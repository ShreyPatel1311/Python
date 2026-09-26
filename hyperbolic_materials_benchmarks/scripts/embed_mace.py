"""Dataset-level delta on MACE-MP-0 (small, E(3)-equivariant) invariant descriptors, mean-pooled per structure.
Graphs: symmetrized kNN (k = 5, 10, 20) with hop distances (HGCN protocol) + raw Euclidean (Khrulkov protocol).
Also reference point clouds: Gaussian (3-D and 256-D), uniform in a hyperbolic disk (H^2), random tree.
"""
import json, os, pickle, sys, time, warnings
import numpy as np, torch, networkx as nx
warnings.filterwarnings("ignore")
torch.set_num_threads(4)
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from run_delta import dataset_level, graph_stats
from ase import Atoms

N = 1000
out = {}
rng = np.random.default_rng(0)

# ---- reference geometries
def h2_points(n, R=6.0, seed=0):
    r_ = np.random.default_rng(seed)
    # uniform w.r.t. hyperbolic area in a disk of radius R: density ~ sinh(r)
    u = r_.random(n); r = np.arccosh(1 + u * (np.cosh(R) - 1)); th = r_.random(n) * 2 * np.pi
    # hyperboloid coordinates -> Euclidean embedding for kNN is not isometric, so use exact H^2 distances
    x = np.stack([np.cosh(r), np.sinh(r) * np.cos(th), np.sinh(r) * np.sin(th)], 1)
    return x

refs = {}
refs["gauss3d"] = rng.normal(size=(N, 3))
refs["gauss256d"] = rng.normal(size=(N, 256))
SKIP_REFS = bool(int(os.environ.get("SKIP_REFS", "0")))  # reference clouds are dataset-independent
for k, X in ({} if SKIP_REFS else refs).items():
    out[f"REF:{k}"] = dataset_level(X)
# H^2: Khrulkov protocol on exact hyperbolic distances + kNN graph on those distances
from hyp import delta_fixed_base, largest_cc, hop_distances, delta_sampled, s_score_sampled, edges_to_adj
Hx = h2_points(N)
G = Hx[:, :1] @ Hx[:, :1].T - Hx[:, 1:] @ Hx[:, 1:].T
Dh = np.arccosh(np.clip(G, 1, None)); np.fill_diagonal(Dh, 0)
fb = [delta_fixed_base(Dh, w) for w in (0, 1, 2)]
resH = {"euclid": {"drel_khrulkov": float(2 * np.mean(fb) / Dh.max()), "note": "exact H^2 distances"}}
for k in (5, 10, 20):
    ind = np.argsort(Dh, 1)[:, 1:k + 1]
    A = edges_to_adj(N, np.stack([np.repeat(np.arange(N), k), ind.ravel()], 1))
    sub, _, frac = largest_cc(A); D = hop_distances(sub)
    hg = [delta_sampled(D, 50000, s) for s in range(5)]
    resH[f"knn{k}"] = dict(n=len(D), diam=float(D.max()), delta_hgcn_max=max(hg), drel_hgcn=2 * max(hg) / D.max(),
                           delta_fixedbase=max(delta_fixed_base(D, w) for w in (0, 1, 2)), s_sampled=s_score_sampled(D))
    resH[f"knn{k}"]["drel_fixedbase"] = 2 * resH[f"knn{k}"]["delta_fixedbase"] / resH[f"knn{k}"]["diam"]
out["REF:H2-disk"] = resH
T = nx.random_labeled_tree(N, seed=0)
out["REF:random-tree"] = graph_stats(nx.to_scipy_sparse_array(T, format="csr"))
print("refs done", json.dumps({k: v.get("knn10", v) for k, v in out.items()}, default=float)[:1500], flush=True)

# ---- MACE embeddings
from mace.calculators import mace_mp
calc = mace_mp(model="small", device=os.environ.get("DEVICE", "cpu"), default_dtype="float32")
samples = pickle.load(open(os.environ.get("SAMPLES", "/tmp/claude-0/data/samples.pkl"), "rb"))
emb = {}
t0 = time.time()
for name, recs in samples.items():
    if not recs:
        continue
    X = []
    for r in recs[:N]:
        a = Atoms(numbers=r["Z"], positions=r["pos"], cell=r["cell"] if r["pbc"] else None, pbc=r["pbc"])
        X.append(calc.get_descriptors(a, invariants_only=True).mean(0))
    X = np.array(X); emb[name] = X
    np.save(f"/tmp/claude-0/data/mace_{name}.npy", X)
    out[name] = dataset_level(X)
    out[name + "|nsub"] = {str(m): dataset_level(X, ks=(10,), seeds=(0,), n_sub=m) for m in (250, 500)}
    print(f"[{time.time()-t0:7.1f}s] {name}: knn10 {out[name]['knn10']} euclid {out[name]['euclid']}", flush=True)
    json.dump(out, open(f"/tmp/claude-0/data/results_mace{os.environ.get('TAG', '')}.json", "w"), indent=1, default=float)
print("DONE")
