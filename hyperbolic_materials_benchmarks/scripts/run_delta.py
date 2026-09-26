"""Compute Gromov delta statistics for every sampled dataset under constructions (a)-(d).

(a) per-structure atomic graphs (crystals): periodic quotient graphs (bond / 5 A / 6 A radius) and
    finite spherical clusters (bond criterion, open boundary)
(b) dataset-level kNN graphs over composition vectors (MACE embeddings in embed_mace.py)
(c) hierarchies: chemical-system inclusion (Hasse) graph; crystal-system > point-group > space-group tree;
    space-group maximal-subgroup graph
(d) molecular bond graphs (QM9, MPcules), with and without H
"""
import itertools, json, pickle, sys, time
import numpy as np
from ase import Atoms
from ase.neighborlist import neighbor_list, natural_cutoffs
from scipy.spatial.distance import cdist
from sklearn.neighbors import NearestNeighbors

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from hyp import (largest_cc, hop_distances, edges_to_adj, delta_sampled, delta_exact, delta_fixed_base,
                 s_score_exact, s_score_sampled)

EXACT_N = 260          # exact four-point delta and s(G) up to this many nodes; HGCN sampling above
N_PER_STRUCT = 200     # structures per dataset for construction (a)/(d)
SAMPLES = 50000        # HGCN protocol


def graph_stats(adj, seed=0):
    sub, idx, frac = largest_cc(adj)
    D = hop_distances(sub)
    n = D.shape[0]
    diam = float(D.max()) if n > 1 else 0.0
    if n < 4:
        return dict(n=n, lcc=frac, diam=diam, delta=0.0, exact=True, s=0.0, drel=0.0)
    if n <= EXACT_N:
        d = float(delta_exact(D)); s = s_score_exact(D); ex = True
    else:
        d = delta_sampled(D, SAMPLES, seed); s = s_score_sampled(D, SAMPLES, seed); ex = False
        d500 = max(delta_sampled(D, 100000, seed + 100 + q) for q in range(5))
        return dict(n=n, lcc=frac, diam=diam, delta=d, exact=ex, s=s, drel=2 * d / diam if diam > 0 else 0.0,
                    delta_500k=d500, drel_500k=2 * d500 / diam if diam > 0 else 0.0)
    return dict(n=n, lcc=frac, diam=diam, delta=d, exact=ex, s=s, drel=2 * d / diam if diam > 0 else 0.0)


def to_atoms(r):
    return Atoms(numbers=r["Z"], positions=r["pos"], cell=r["cell"], pbc=r["pbc"])


def quotient_graph(r, cutoff=None, mult=None):
    a = to_atoms(r)
    cut = natural_cutoffs(a, mult=mult) if mult is not None else cutoff
    i, j = neighbor_list("ij", a, cut)
    return edges_to_adj(len(a), np.stack([i, j], 1))


def cluster_graph(r, R=8.0, mult=1.2, seed=0):
    a = to_atoms(r)
    c = np.random.default_rng(seed).integers(len(a))
    i, j, Dv = neighbor_list("ijD", a, R)
    m = i == c
    pos = np.vstack([a.positions[c][None], a.positions[c] + Dv[m]])
    Z = np.concatenate([[a.numbers[c]], a.numbers[j[m]]])
    rad = np.array(natural_cutoffs(Atoms(numbers=Z), mult=mult))
    dd = cdist(pos, pos)
    ii, jj = np.where((dd < rad[:, None] + rad[None, :]) & (dd > 1e-6))
    return edges_to_adj(len(Z), np.stack([ii, jj], 1))


def molecule_graph(r, mult=1.2, use_sdf=False, heavy_only=False):
    Z = r["Z"]
    if use_sdf and r["bonds"] is not None:
        e = r["bonds"]
    else:
        rad = np.array(natural_cutoffs(Atoms(numbers=Z), mult=mult))
        dd = cdist(r["pos"], r["pos"])
        ii, jj = np.where((dd < rad[:, None] + rad[None, :]) & (dd > 1e-6))
        e = np.stack([ii, jj], 1)
    if heavy_only:
        keep = np.where(Z > 1)[0]
        remap = -np.ones(len(Z), int); remap[keep] = np.arange(len(keep))
        e = remap[e]; e = e[(e >= 0).all(1)]
        return edges_to_adj(len(keep), e)
    return edges_to_adj(len(Z), e)


def agg(stats):
    d = np.array([s["delta"] for s in stats]); dr = np.array([s["drel"] for s in stats])
    s = np.array([s["s"] for s in stats]); n = np.array([s["n"] for s in stats]); di = np.array([x["diam"] for x in stats])
    lcc = np.array([x["lcc"] for x in stats])
    return dict(count=len(stats), n_med=float(np.median(n)), diam_med=float(np.median(di)),
                delta_mean=float(d.mean()), delta_std=float(d.std()), delta_max=float(d.max()),
                frac_tree=float((d == 0).mean()), drel_mean=float(dr.mean()), drel_std=float(dr.std()),
                s_mean=float(s.mean()), s_std=float(s.std()), lcc_mean=float(lcc.mean()),
                exact_frac=float(np.mean([x["exact"] for x in stats])),
                frac_diam_le2=float((di <= 2).mean()))


# ---------------------------------------------------------------- (b) dataset-level graphs
def comp_vec(r):
    v = np.bincount(r["Z"], minlength=119).astype(float)
    return v / v.sum()


def knn_adj(X, k):
    nn = NearestNeighbors(n_neighbors=k + 1).fit(X)
    _, ind = nn.kneighbors(X)
    e = np.stack([np.repeat(np.arange(len(X)), k), ind[:, 1:].ravel()], 1)
    return edges_to_adj(len(X), e)


def dataset_level(X, ks=(5, 10, 20), seeds=(0, 1, 2, 3, 4), n_sub=None, sub_seed=0):
    if n_sub is not None and n_sub < len(X):
        X = X[np.random.default_rng(sub_seed).choice(len(X), n_sub, replace=False)]
    res = {}
    for k in ks:
        sub, idx, frac = largest_cc(knn_adj(X, k))
        D = hop_distances(sub)
        diam = float(D.max())
        hg = [delta_sampled(D, SAMPLES, s) for s in seeds]
        d500 = max(delta_sampled(D, 100000, 100 + q) for q in range(5))
        fb = max(delta_fixed_base(D, w) for w in np.random.default_rng(0).choice(len(D), 3, replace=False))
        sc = s_score_sampled(D, SAMPLES, 0)
        res[f"knn{k}"] = dict(n=len(D), lcc=frac, diam=diam, delta_hgcn_max=max(hg), delta_hgcn_mean=float(np.mean(hg)),
                              delta_fixedbase=fb, delta_500k=d500, drel_hgcn=2 * max(hg) / diam, drel_fixedbase=2 * fb / diam, s_sampled=sc)
    # Khrulkov protocol on raw Euclidean distances
    E = cdist(X, X)
    fbs = [delta_fixed_base(E, w) for w in np.random.default_rng(1).choice(len(E), 3, replace=False)]
    res["euclid"] = dict(n=len(E), diam=float(E.max()), drel_khrulkov=float(2 * np.mean(fbs) / E.max()),
                         drel_khrulkov_std=float(2 * np.std(fbs) / E.max()))
    return res


# ---------------------------------------------------------------- (c) hierarchies
def chemsys_hasse(chemsyss):
    nodes = set()
    for cs in chemsyss:
        els = tuple(sorted(cs.split("-")))
        for r in range(1, len(els) + 1):
            nodes.update(itertools.combinations(els, r))
    nodes = sorted(nodes); ix = {s: i for i, s in enumerate(nodes)}
    e = [(ix[s], ix[tuple(x for x in s if x != el)]) for s in nodes if len(s) > 1 for el in s]
    return edges_to_adj(len(nodes), np.array(e) if e else np.zeros((0, 2), int))


def symmetry_tree(spgs):
    from pymatgen.symmetry.groups import SpaceGroup
    nodes = {"root": 0}; e = []
    def nid(k):
        if k not in nodes: nodes[k] = len(nodes)
        return nodes[k]
    for n in sorted(set(x for x in spgs if x)):
        sg = SpaceGroup.from_int_number(int(n))
        cs, pg = sg.crystal_system, sg.point_group
        e += [(nid("root"), nid("cs:" + cs)), (nid("cs:" + cs), nid("pg:" + pg)), (nid("pg:" + pg), nid(f"sg:{n}"))]
    return edges_to_adj(len(nodes), np.array(e))


def spacegroup_subgroup_graph(spgs=None):
    from pymatgen.symmetry.groups import SYMM_DATA
    ms = {int(k): v for k, v in SYMM_DATA["maximal_subgroups"].items()}
    e = [(g - 1, h - 1) for g, subs in ms.items() for h in subs if h != g]
    A = edges_to_adj(230, np.array(e))
    if spgs is not None:
        keep = np.array(sorted(set(int(x) for x in spgs if x))) - 1
        A = A[keep][:, keep]
    return A


if __name__ == "__main__":
    samples = pickle.load(open("/tmp/claude-0/data/samples.pkl", "rb"))
    results = {"meta": dict(EXACT_N=EXACT_N, N_PER_STRUCT=N_PER_STRUCT, SAMPLES=SAMPLES)}
    t0 = time.time()
    for name, recs in samples.items():
        if not recs:
            continue
        R = {"targets": recs[0]["targets"], "pool": len(recs)}
        sub = recs[:N_PER_STRUCT]
        if recs[0]["pbc"]:
            variants = {"Q-bond1.2": lambda r: quotient_graph(r, mult=1.2),
                        "Q-r5": lambda r: quotient_graph(r, cutoff=5.0),
                        "Q-r6": lambda r: quotient_graph(r, cutoff=6.0),
                        "C8-bond1.2": lambda r: cluster_graph(r, 8.0, 1.2)}
            abl = {"C8-bond1.1": lambda r: cluster_graph(r, 8.0, 1.1),
                   "C8-bond1.3": lambda r: cluster_graph(r, 8.0, 1.3),
                   "C6-bond1.2": lambda r: cluster_graph(r, 6.0, 1.2),
                   "C10-bond1.2": lambda r: cluster_graph(r, 10.0, 1.2)}
        else:
            variants = {"M-bond1.2": lambda r: molecule_graph(r, 1.2),
                        "M-bond1.2-noH": lambda r: molecule_graph(r, 1.2, heavy_only=True)}
            if name == "QM9":
                variants["M-sdf"] = lambda r: molecule_graph(r, use_sdf=True)
                variants["M-sdf-noH"] = lambda r: molecule_graph(r, use_sdf=True, heavy_only=True)
            abl = {"M-bond1.1": lambda r: molecule_graph(r, 1.1), "M-bond1.3": lambda r: molecule_graph(r, 1.3)}
        R["per_structure"] = {}
        for vn, f in variants.items():
            R["per_structure"][vn] = agg([graph_stats(f(r)) for r in sub])
        R["per_structure_ablation"] = {}
        for vn, f in abl.items():
            R["per_structure_ablation"][vn] = agg([graph_stats(f(r)) for r in sub[:50]])
        # (b) composition kNN graph (MACE in separate script)
        X = np.array([comp_vec(r) for r in recs[:1000]])
        R["dataset_comp"] = dataset_level(X)
        R["dataset_comp_nsub"] = {str(m): dataset_level(X, ks=(10,), seeds=(0,), n_sub=m) for m in (250, 500)}
        # (c) hierarchies
        R["chemsys_hasse"] = graph_stats(chemsys_hasse([r["chemsys"] for r in recs[:1000]]))
        spgs = [r["spg"] for r in recs[:1000] if r.get("spg")]
        if spgs:
            R["symmetry_tree"] = graph_stats(symmetry_tree(spgs))
            R["spg_subgroup_induced"] = graph_stats(spacegroup_subgroup_graph(spgs))
            R["n_spacegroups"] = len(set(spgs))
        results[name] = R
        print(f"[{time.time()-t0:7.1f}s] {name}: " + json.dumps(R["per_structure"], default=float)[:400], flush=True)
        json.dump(results, open("/tmp/claude-0/data/results_main.json", "w"), indent=1, default=float)
    results["spg_subgroup_full230"] = graph_stats(spacegroup_subgroup_graph())
    json.dump(results, open("/tmp/claude-0/data/results_main.json", "w"), indent=1, default=float)
    print("DONE", time.time() - t0)
