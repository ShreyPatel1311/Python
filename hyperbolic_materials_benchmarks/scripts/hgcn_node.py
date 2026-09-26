"""Node-level (per-atom) regression of rotation-invariant parts of per-atom tensors with the HGCN repo encoder
(Chami et al. 2019, arXiv:1910.12933; PoincareBall, one trainable curvature per layer, args.c = None) vs the repo's
Euclidean GCN encoder, identical head / training.
Targets: EFG  - JARVIS dft_3d electric-field-gradient eigenvalues, sorted ascending (3 per atom; efg_data.py)
         <SRC> (MP-ALOE, MatPES)        - per-atom force magnitude |F| (eV/A)
         <SRC>:F  for SRC in MPtrj, MP-ALOE, MatPES, OC20 (S2EF 200K, raw forces incl. fixed atoms), OMat24r / OMat24a
                  (OMat24 val rattled-300-subsampled / aimd-from-PBE-3000-nvt)  - |F| (eV/A)
         <SRC>:mag for SRC in MPtrj, MP-ALOE, MatPES   - |magnetic moment| per atom (muB; sign of collinear moments dropped)
         MatPES:bader                                 - Bader charge per atom (as stored)
         Rows without the target are skipped. A per-element mean baseline (train-set mean per Z) is also reported.
Graph per structure: periodic quotient graph, radius 5 A (ASE neighbor_list), unweighted; node features = one-hot Z
(same construction as hgcn_energy.py). HGCN takes no coordinates, so geometry enters only through graph connectivity.
Divergence fix as in hgcn_sweep.py FIX=clip+cbound: gradient-norm clip 1.0, curvatures clamped to [0.01, 100].
Usage: hgcn_node.py <EFG|MP-ALOE|MatPES> <HGCN|GCN> <seed> <max_epochs> [n_structures]
"""
import json, os, pickle, sys, time
import numpy as np, scipy.sparse as sp, torch, torch.nn as nn
sys.path.insert(0, os.environ.get("HGCN", "/tmp/claude-0/hgcn"))
from config import parser
from models import encoders
from utils.data_utils import normalize
import manifolds

torch.set_default_dtype(torch.float64)
torch.set_num_threads(int(os.environ.get("NT", "4")))
DS, MODEL, SEED, MAX_EP = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
N = int(sys.argv[5]) if len(sys.argv) > 5 else (1500 if DS == "EFG" else 600)
SRC, TGT = (DS.split(":") + ["F"])[:2]
D = "/tmp/claude-0/data"; OUT = os.environ.get("OUT", D)
C_MIN, C_MAX, PATIENCE = 0.01, 100.0, 20

# ------------------------------------------------------------------ data
cache = f"{D}/node_{DS.replace(':', '_')}_{N}.pkl"
if os.path.exists(cache):
    S = pickle.load(open(cache, "rb"))
else:
    from ase import Atoms
    from ase.neighborlist import neighbor_list
    rng7 = np.random.default_rng(7)
    if DS == "EFG":
        S = [dict(Z=r["Z"], pos=r["pos"], cell=r["cell"], y=r["eig"]) for r in pickle.load(open(f"{D}/efg_{N}.pkl", "rb"))]
    elif SRC in ("MPtrj", "MP-ALOE", "MatPES"):
        import pyarrow.parquet as pq
        pf = pq.ParquetFile(f"{D}/{dict(MPtrj='mptrj', MatPES='matpes').get(SRC, 'mpaloe')}.parquet")
        col = dict(F="forces", mag="magmoms", bader="bader_charges")[TGT]
        if TGT == "F":
            rows = np.sort(rng7.choice(pf.metadata.num_rows, size=N, replace=False))
        else:   # rows that carry the target
            has = np.array([v is not None and len(v) > 0 and None not in v for v in pf.read(columns=[col]).column(0).to_pylist()])
            rows = np.sort(rng7.choice(np.where(has)[0], size=min(N, int(has.sum())), replace=False))
        t = pf.read(columns=["atomic_numbers", "cart_coords", "cell", col]).take(rows).to_pydict()
        f = {"F": lambda v: np.linalg.norm(np.array(v), axis=1), "mag": lambda v: np.abs(np.array(v, float)),
             "bader": lambda v: np.array(v, float)}[TGT]
        S = [dict(Z=np.array(t["atomic_numbers"][k]), pos=np.array(t["cart_coords"][k]), cell=np.array(t["cell"][k]),
                  y=f(t[col][k])[:, None]) for k in range(len(rows))]
    elif SRC == "OC20":
        import io, lzma, tarfile
        from ase.io import read
        tf = tarfile.open(f"{D}/s2ef_train_200K.tar")
        name = sorted(m for m in tf.getnames() if m.endswith(".extxyz.xz"))[3]
        fr = read(io.StringIO(lzma.decompress(tf.extractfile(name).read()).decode()), index=":", format="extxyz")
        S = [dict(Z=a.numbers.copy(), pos=a.positions.copy(), cell=np.array(a.cell),
                  y=np.linalg.norm(a.get_forces(apply_constraint=False), axis=1)[:, None])
             for a in (fr[k] for k in np.sort(rng7.choice(len(fr), size=N, replace=False)))]
    elif SRC in ("OMat24r", "OMat24a"):
        from ase.db import connect
        db = connect(f"{D}/{dict(OMat24r='rattled-300-subsampled', OMat24a='aimd-from-PBE-3000-nvt')[SRC]}/data.aselmdb", type="aselmdb")
        S = []
        for i in np.sort(rng7.choice(db.count(), size=N, replace=False)):
            a = db.get(int(i) + 1).toatoms()
            S.append(dict(Z=a.numbers.copy(), pos=a.positions.copy(), cell=np.array(a.cell),
                          y=np.linalg.norm(a.get_forces(apply_constraint=False), axis=1)[:, None]))
    else:
        raise SystemExit(f"unknown dataset {DS}")
    for s in S:
        a = Atoms(numbers=s["Z"], positions=s["pos"], cell=s["cell"], pbc=True)
        i, j = neighbor_list("ij", a, 5.0)
        e = np.unique(np.stack([i, j], 1), axis=0); s["e"] = e[e[:, 0] != e[:, 1]]
    pickle.dump(S, open(cache, "wb"))
G = len(S)
perm = np.random.default_rng(123).permutation(G)           # split by structure, shared by all models / seeds
tr, va, te = perm[: int(.8 * G)], perm[int(.8 * G): int(.9 * G)], perm[int(.9 * G):]
ytr = np.concatenate([S[g]["y"] for g in tr]); mu, sd = ytr.mean(0), ytr.std(0)
ZMAX = 100


def onehot(z):
    x = np.zeros((len(z), ZMAX)); x[np.arange(len(z)), np.minimum(z, ZMAX - 1)] = 1; return x


PG = []
for s in S:
    n = len(s["Z"]); r, c = s["e"].T
    A = sp.csr_matrix((np.ones(len(r)), (r, c)), shape=(n, n)); A.data[:] = 1
    A = normalize(A + sp.eye(n)).tocoo()
    PG.append((torch.tensor(onehot(s["Z"])), torch.tensor(np.vstack([A.row, A.col])), torch.tensor(A.data),
               torch.tensor((s["y"] - mu) / sd)))


def batch(idx):
    xs, ind, val, ys, off = [], [], [], [], 0
    for g in idx:
        x, i, v, y = PG[g]; xs.append(x); ind.append(i + off); val.append(v); ys.append(y); off += len(x)
    return torch.cat(xs), torch.sparse_coo_tensor(torch.cat(ind, 1), torch.cat(val), (off, off)).coalesce(), torch.cat(ys)


# ------------------------------------------------------------------ model (HGCN repo encoder, as hgcn_energy.py)
args = parser.parse_args([])
args.model = MODEL; args.manifold = "PoincareBall" if MODEL == "HGCN" else "Euclidean"
args.dim, args.num_layers, args.act, args.bias, args.dropout = 64, 3, "relu", 1, 0.0
args.feat_dim, args.task, args.device, args.c = ZMAX, "lp", "cpu", None if MODEL == "HGCN" else 1.0
args.use_att, args.local_agg, args.n_nodes = 0, 0, 1
NY = PG[0][3].shape[1]


class Net(nn.Module):
    def __init__(self):
        super().__init__()
        self.c = nn.Parameter(torch.tensor([1.0])) if MODEL == "HGCN" else torch.tensor([1.0])
        self.enc = getattr(encoders, MODEL)(self.c, args)
        self.man = getattr(manifolds, args.manifold)()
        self.head = nn.Sequential(nn.Linear(args.dim, 64), nn.SiLU(), nn.Linear(64, NY))
    def curv(self):   # encoder.curvatures = per-layer curvatures + self.c (appended by the HGCN encoder)
        return [p for p in getattr(self.enc, "curvatures", []) if isinstance(p, nn.Parameter)]
    def forward(self, x, A):
        h = self.enc.encode(x, A)
        if MODEL == "HGCN":
            h = self.man.logmap0(h, c=self.c)
        return self.head(h)


torch.manual_seed(SEED); np.random.seed(SEED)
net = Net(); opt = torch.optim.Adam(net.parameters(), lr=1e-3)
vb = [batch(va[i:i + 64]) for i in range(0, len(va), 64)]
tb = [batch(te[i:i + 64]) for i in range(0, len(te), 64)]


def evaluate(bs):
    net.eval(); err = []
    with torch.no_grad():
        for x, A, y in bs:
            err.append(((net(x, A) - y) * torch.tensor(sd)).abs())
    e = torch.cat(err); return e.mean(0).tolist(), float(e.mean())


best, best_state, best_ep, bad, t0, diverged, log = 1e18, None, 0, 0, time.time(), False, []
for ep in range(MAX_EP):
    net.train(); p = np.random.permutation(tr)
    for i in range(0, len(p), 16):
        x, A, y = batch(p[i:i + 16])
        loss = ((net(x, A) - y) ** 2).mean()
        if not torch.isfinite(loss):
            diverged = True; break
        opt.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0); opt.step()
        with torch.no_grad():
            for c in net.curv():
                c.clamp_(C_MIN, C_MAX)
    if diverged:
        break
    _, v = evaluate(vb)
    log.append(dict(ep=ep + 1, val_MAE=round(v, 5), c=[round(float(c), 4) for c in net.curv()]))
    if v < best:
        best, best_ep, bad = v, ep + 1, 0; best_state = {k: t.clone() for k, t in net.state_dict().items()}
    else:
        bad += 1
        if bad >= PATIENCE:
            break
curv_last = [float(c) for c in net.curv()]
if best_state is not None:
    net.load_state_dict(best_state)
test_per, test_mae = evaluate(tb)
ztr = np.concatenate([S[g]["Z"] for g in tr]); zte = np.concatenate([S[g]["Z"] for g in te])
yte = np.concatenate([S[g]["y"] for g in te])
zmean = {z: ytr[ztr == z].mean(0) for z in np.unique(ztr)}
per_el = float(np.mean(np.abs(yte - np.array([zmean.get(z, mu) for z in zte]))))
res = dict(dataset=DS, model=MODEL, seed=SEED, n_structures=G, n_train_atoms=int(len(ytr)), target_sd=sd.tolist(),
           epochs_run=len(log), best_epoch=best_ep, diverged=diverged, sec=round(time.time() - t0, 1),
           test_MAE=test_mae, test_MAE_per_target=test_per, mean_baseline_MAE=float(np.mean(np.abs(
               np.concatenate([S[g]["y"] for g in te]) - mu))), per_element_baseline_MAE=per_el,
           curvature_best=[float(c) for c in net.curv()], curvature_last=curv_last,
           curvature_at_bound=[bool(c <= C_MIN + 1e-9 or c >= C_MAX - 1e-9) for c in curv_last], curve=log)
print("RESULT " + json.dumps({k: v for k, v in res.items() if k != "curve"}), flush=True)
json.dump(res, open(f"{OUT}/node_{DS.replace(':', '_')}_{MODEL}_s{SEED}.json", "w"))
