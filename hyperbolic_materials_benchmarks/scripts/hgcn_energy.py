"""Graph-level regression of MPtrj energy per atom with the HGCN repo encoder (PoincareBall, trainable curvature)
vs the repo's Euclidean GCN encoder, identical head/training. Baselines: train mean; per-element linear fit.
Graph per structure: periodic quotient graph, radius 5 A (ASE neighbor_list), unweighted; node features = one-hot Z.
HGCN has no coordinate/distance input, so it cannot express equivariant targets (forces/stress); energy/atom is the
rank-0 target it can predict.
Usage: hgcn_energy.py <model HGCN|GCN> <seed> <max_epochs> [n_structures]"""
import json, os, sys, time
import numpy as np, scipy.sparse as sp, torch, torch.nn as nn
sys.path.insert(0, "/tmp/claude-0/hgcn")
from config import parser
from models import encoders
from utils.data_utils import normalize, sparse_mx_to_torch_sparse_tensor
import manifolds

torch.set_default_dtype(torch.float64)
torch.set_num_threads(int(os.environ.get("NT", "4")))
MODEL, SEED, MAX_EP = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
N = int(sys.argv[4]) if len(sys.argv) > 4 else 3000
CACHE = f"/tmp/claude-0/data/energy_graphs_{N}.npz"

# ------------------------------------------------------------------ data (fixed sample, seed 7)
if not os.path.exists(CACHE):
    import pyarrow.parquet as pq
    from ase import Atoms
    from ase.neighborlist import neighbor_list
    pf = pq.ParquetFile("/tmp/claude-0/data/mptrj.parquet")
    prov = pf.read(columns=["provenance"]).column(0).to_pylist()
    mids = np.array([p["material_id"] if p else f"none{i}" for i, p in enumerate(prov)])
    rng = np.random.default_rng(7)
    order = rng.permutation(len(mids)); seen, rows = set(), []
    for r in order:
        if mids[r] not in seen:
            seen.add(mids[r]); rows.append(r)
            if len(rows) == N:
                break
    rows = np.sort(np.array(rows))
    t = pf.read(columns=["atomic_numbers", "cart_coords", "cell", "energy", "nsites"]).take(rows).to_pydict()
    Zs, E, EI, EJ, NA = [], [], [], [], []
    for i in range(len(rows)):
        a = Atoms(numbers=t["atomic_numbers"][i], positions=t["cart_coords"][i], cell=t["cell"][i], pbc=True)
        ii, jj = neighbor_list("ij", a, 5.0)
        e = np.unique(np.stack([ii, jj], 1), axis=0); e = e[e[:, 0] != e[:, 1]]
        Zs.append(np.array(t["atomic_numbers"][i])); E.append(t["energy"][i] / t["nsites"][i])
        EI.append(e[:, 0]); EJ.append(e[:, 1]); NA.append(len(a))
    np.savez(CACHE, Z=np.concatenate(Zs), E=np.array(E), NA=np.array(NA),
             EI=np.concatenate(EI), EJ=np.concatenate(EJ), NE=np.array([len(x) for x in EI]), rows=rows)
D = np.load(CACHE)
NA, NE, E = D["NA"], D["NE"], D["E"]
na_off = np.r_[0, np.cumsum(NA)]; ne_off = np.r_[0, np.cumsum(NE)]
G = len(NA)
split_rng = np.random.default_rng(123)           # fixed split shared by all models/seeds
perm = split_rng.permutation(G)
tr, va, te = perm[: int(.8 * G)], perm[int(.8 * G): int(.9 * G)], perm[int(.9 * G):]
Zall = D["Z"]; zmax = 95
def onehot(z):
    x = np.zeros((len(z), zmax)); x[np.arange(len(z)), np.minimum(z, zmax - 1)] = 1; return x

# baselines
comp = np.zeros((G, zmax))
for g in range(G):
    np.add.at(comp[g], np.minimum(Zall[na_off[g]:na_off[g + 1]], zmax - 1), 1.0 / NA[g])
base = {"mean_MAE": float(np.abs(E[te] - E[tr].mean()).mean())}
w, *_ = np.linalg.lstsq(comp[tr], E[tr], rcond=None)
base["per_element_linear_MAE"] = float(np.abs(comp[te] @ w - E[te]).mean())
mu, sd = E[tr].mean(), E[tr].std()

# precompute per-graph row-normalised (A + I) blocks once (repo preprocessing is per-row, so block-diagonal exact)
PG = []
for g in range(G):
    n = NA[g]
    r = D["EI"][ne_off[g]:ne_off[g + 1]]; c = D["EJ"][ne_off[g]:ne_off[g + 1]]
    A = sp.csr_matrix((np.ones(len(r)), (r, c)), shape=(n, n)); A.data[:] = 1
    A = normalize(A + sp.eye(n)).tocoo()
    PG.append((torch.tensor(onehot(Zall[na_off[g]:na_off[g + 1]])), torch.tensor(np.vstack([A.row, A.col])),
               torch.tensor(A.data)))

def batch(idx):
    xs, ind, val, gid, off = [], [], [], [], 0
    for k, g in enumerate(idx):
        x, i, v = PG[g]; xs.append(x); ind.append(i + off); val.append(v)
        gid.append(torch.full((len(x),), k)); off += len(x)
    A = torch.sparse_coo_tensor(torch.cat(ind, 1), torch.cat(val), (off, off)).coalesce()
    return torch.cat(xs), A, torch.cat(gid), torch.tensor((E[idx] - mu) / sd)

# ------------------------------------------------------------------ model
args = parser.parse_args([])
args.model = MODEL; args.manifold = "PoincareBall" if MODEL == "HGCN" else "Euclidean"
args.dim, args.num_layers, args.act, args.bias, args.dropout = 64, 3, "relu", 1, 0.0
args.feat_dim, args.task, args.device, args.c = zmax, "lp", "cpu", None if MODEL == "HGCN" else 1.0
args.use_att, args.local_agg, args.n_nodes = 0, 0, 1


class Net(nn.Module):
    def __init__(self):
        super().__init__()
        self.c = nn.Parameter(torch.tensor([1.0])) if MODEL == "HGCN" else torch.tensor([1.0])
        self.enc = getattr(encoders, MODEL)(self.c, args)
        self.man = getattr(manifolds, args.manifold)()
        self.head = nn.Sequential(nn.Linear(args.dim, 64), nn.SiLU(), nn.Linear(64, 1))
    def forward(self, x, A, gid, ng):
        h = self.enc.encode(x, A)
        if MODEL == "HGCN":
            h = self.man.logmap0(h, c=self.c)     # hyperbolic node embeddings -> tangent space at origin
        pooled = torch.zeros(ng, h.shape[1]).index_add_(0, gid, h) / torch.bincount(gid, minlength=ng)[:, None]
        return self.head(pooled).squeeze(-1)


torch.manual_seed(SEED); np.random.seed(SEED)
net = Net(); opt = torch.optim.Adam(net.parameters(), lr=1e-3)
vb = [batch(va[i:i + 256]) for i in range(0, len(va), 256)]
tb = [batch(te[i:i + 256]) for i in range(0, len(te), 256)]
def evaluate(bs):
    net.eval(); err = []
    with torch.no_grad():
        for x, A, gid, y in bs:
            err.append(((net(x, A, gid, len(y)) - y) * sd).abs())
    return float(torch.cat(err).mean())
best, best_state, best_ep, bad, t0, diverged, log = 1e9, None, 0, 0, time.time(), False, []
for ep in range(MAX_EP):
    net.train(); p = np.random.permutation(tr)
    for i in range(0, len(p), 64):
        x, A, gid, y = batch(p[i:i + 64])
        loss = ((net(x, A, gid, len(y)) - y) ** 2).mean()
        if not torch.isfinite(loss):
            diverged = True; break
        opt.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0); opt.step()
    if diverged:
        break
    v = evaluate(vb); log.append(round(v, 5))
    if v < best:
        best, best_ep, bad = v, ep + 1, 0; best_state = {k: t.clone() for k, t in net.state_dict().items()}
    else:
        bad += 1
        if bad >= 30:
            break
if best_state is not None:
    net.load_state_dict(best_state)
res = dict(model=MODEL, seed=SEED, n_structures=G, n_train=len(tr), epochs_run=len(log), best_epoch=best_ep,
           diverged=diverged, sec=round(time.time() - t0, 1), sec_per_epoch=round((time.time() - t0) / max(len(log), 1), 2),
           val_MAE=best, test_MAE=evaluate(tb), baselines=base, target_std=float(sd),
           curvature=float(net.c.detach()) if MODEL == "HGCN" else None, val_curve=log)
print(json.dumps({k: v for k, v in res.items() if k != "val_curve"}), flush=True)
json.dump(res, open(f"/tmp/claude-0/data/energy_{MODEL}_s{SEED}_n{G}.json", "w"))
