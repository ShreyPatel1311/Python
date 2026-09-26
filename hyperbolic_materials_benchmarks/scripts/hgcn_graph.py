"""Graph-level (per-structure) regression of rotation-invariant tensor targets (tensor_targets.py) with the HGCN repo
encoder (Chami et al. 2019, arXiv:1910.12933; PoincareBall, one trainable curvature per layer, args.c = None) vs the
repo's Euclidean GCN encoder, identical head / training (as hgcn_energy.py): 5 A periodic quotient graph, unweighted,
one-hot Z features, log_0 of node states -> mean pooling -> MLP. Targets standardised per component; MSE loss.
Divergence fix as hgcn_sweep.py FIX=clip+cbound (grad-norm clip 1.0, curvatures clamped to [0.01, 100]).
Curvatures reported: encoder.curvatures = [c_1, c_2, c_3, c_out]; c_out is the curvature of the last layer's output,
which the log_0 readout at the same curvature cancels, so only c_1..c_3 carry information.
Usage: hgcn_graph.py <dataset> <HGCN|GCN> <seed> <max_epochs>
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
D = "/tmp/claude-0/data"; OUT = os.environ.get("OUT", D)
C_MIN, C_MAX, PATIENCE, ZMAX = 0.01, 100.0, 20, 100

cache = f"{D}/ttg_{DS}.pkl"
if os.path.exists(cache):
    S = pickle.load(open(cache, "rb"))
else:
    from ase import Atoms
    from ase.neighborlist import neighbor_list
    S = pickle.load(open(f"{D}/tt_{DS}.pkl", "rb"))
    for s in S:
        a = Atoms(numbers=s["Z"], positions=s["pos"], cell=s["cell"], pbc=True)
        i, j = neighbor_list("ij", a, 5.0)
        e = np.unique(np.stack([i, j], 1), axis=0); s["e"] = e[e[:, 0] != e[:, 1]]
    pickle.dump(S, open(cache, "wb"))
G = len(S)
perm = np.random.default_rng(123).permutation(G)
tr, va, te = perm[: int(.8 * G)], perm[int(.8 * G): int(.9 * G)], perm[int(.9 * G):]
Y = np.array([s["y"] for s in S], float); mu, sd = Y[tr].mean(0), Y[tr].std(0)
sd = np.where(sd > 0, sd, 1.0)


def onehot(z):
    x = np.zeros((len(z), ZMAX)); x[np.arange(len(z)), np.minimum(z, ZMAX - 1)] = 1; return x


PG = []
for s in S:
    n = len(s["Z"]); r, c = s["e"].T
    A = sp.csr_matrix((np.ones(len(r)), (r, c)), shape=(n, n)); A.data[:] = 1
    A = normalize(A + sp.eye(n)).tocoo()
    PG.append((torch.tensor(onehot(s["Z"])), torch.tensor(np.vstack([A.row, A.col])), torch.tensor(A.data)))


def batch(idx):
    xs, ind, val, gid, off = [], [], [], [], 0
    for k, g in enumerate(idx):
        x, i, v = PG[g]; xs.append(x); ind.append(i + off); val.append(v); gid.append(torch.full((len(x),), k)); off += len(x)
    A = torch.sparse_coo_tensor(torch.cat(ind, 1), torch.cat(val), (off, off)).coalesce()
    return torch.cat(xs), A, torch.cat(gid), torch.tensor((Y[idx] - mu) / sd)


args = parser.parse_args([])
args.model = MODEL; args.manifold = "PoincareBall" if MODEL == "HGCN" else "Euclidean"
args.dim, args.num_layers, args.act, args.bias, args.dropout = 64, 3, "relu", 1, 0.0
args.feat_dim, args.task, args.device, args.c = ZMAX, "lp", "cpu", None if MODEL == "HGCN" else 1.0
args.use_att, args.local_agg, args.n_nodes = 0, 0, 1
NY = Y.shape[1]


class Net(nn.Module):
    def __init__(self):
        super().__init__()
        self.c = nn.Parameter(torch.tensor([1.0])) if MODEL == "HGCN" else torch.tensor([1.0])
        self.enc = getattr(encoders, MODEL)(self.c, args)
        self.man = getattr(manifolds, args.manifold)()
        self.head = nn.Sequential(nn.Linear(args.dim, 64), nn.SiLU(), nn.Linear(64, NY))
    def curv(self):
        return [p for p in getattr(self.enc, "curvatures", []) if isinstance(p, nn.Parameter)]
    def forward(self, x, A, gid, ng):
        h = self.enc.encode(x, A)
        if MODEL == "HGCN":
            h = self.man.logmap0(h, c=self.c)
        pooled = torch.zeros(ng, h.shape[1]).index_add_(0, gid, h) / torch.bincount(gid, minlength=ng)[:, None]
        return self.head(pooled)


torch.manual_seed(SEED); np.random.seed(SEED)
net = Net(); opt = torch.optim.Adam(net.parameters(), lr=1e-3)
vb = [batch(va[i:i + 64]) for i in range(0, len(va), 64)]
tb = [batch(te[i:i + 64]) for i in range(0, len(te), 64)]


def evaluate(bs):
    net.eval(); err = []
    with torch.no_grad():
        for x, A, gid, y in bs:
            err.append(((net(x, A, gid, len(y)) - y) * torch.tensor(sd)).abs())
    e = torch.cat(err); return e.mean(0).tolist(), float((e / torch.tensor(sd)).mean())


best, best_state, best_ep, bad, t0, diverged, log = 1e18, None, 0, 0, time.time(), False, []
for ep in range(MAX_EP):
    net.train(); p = np.random.permutation(tr)
    for i in range(0, len(p), 32):
        x, A, gid, y = batch(p[i:i + 32])
        loss = ((net(x, A, gid, len(y)) - y) ** 2).mean()
        if not torch.isfinite(loss):
            diverged = True; break
        opt.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0); opt.step()
        with torch.no_grad():
            for c in net.curv():
                c.clamp_(C_MIN, C_MAX)
    if diverged:
        break
    _, v = evaluate(vb)
    log.append(dict(ep=ep + 1, val=round(v, 5), c=[round(float(c), 4) for c in net.curv()]))
    if v < best:
        best, best_ep, bad = v, ep + 1, 0; best_state = {k: t.clone() for k, t in net.state_dict().items()}
    else:
        bad += 1
        if bad >= PATIENCE:
            break
curv_last = [float(c) for c in net.curv()]
if best_state is not None:
    net.load_state_dict(best_state)
per, _ = evaluate(tb)
res = dict(dataset=DS, model=MODEL, seed=SEED, n_structures=G, n_train=len(tr), target_mean=mu.tolist(), target_sd=sd.tolist(),
           epochs_run=len(log), best_epoch=best_ep, diverged=diverged, sec=round(time.time() - t0, 1),
           test_MAE=per, mean_baseline_MAE=np.abs(Y[te] - mu).mean(0).tolist(),
           curvature_best=[float(c) for c in net.curv()], curvature_last=curv_last,
           curvature_at_bound=[bool(c <= C_MIN + 1e-9 or c >= C_MAX - 1e-9) for c in curv_last], curve=log)
print("RESULT " + json.dumps({k: v for k, v in res.items() if k != "curve"}), flush=True)
json.dump(res, open(f"{OUT}/graph_{DS}_{MODEL}_s{SEED}.json", "w"))
