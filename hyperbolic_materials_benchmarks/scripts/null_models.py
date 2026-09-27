"""Matched null models for dataset-level delta: per-feature independent permutation of the same embedding
matrix (keeps each feature's marginal distribution and the dimension, destroys joint structure).
Reported as the difference observed - null (negative = more tree-like than the matched null)."""
import glob, json, os, pickle, sys
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from run_delta import dataset_level, comp_vec

def permute_null(X, seed):
    r = np.random.default_rng(seed)
    return np.column_stack([X[r.permutation(len(X)), j] for j in range(X.shape[1])])

out = {}
samples = pickle.load(open(os.environ.get("SAMPLES", "/tmp/claude-0/data/samples.pkl"), "rb"))
for f in sorted(glob.glob("/tmp/claude-0/data/mace_*.npy")):
    name = f.split("mace_")[1][:-4]
    if name not in samples:
        continue
    X = np.load(f)
    Xc = np.array([comp_vec(r) for r in samples[name][:1000]])
    res = {}
    for tag, M in (("mace", X), ("comp", Xc)):
        if np.allclose(M, M[0]):
            res[tag] = "degenerate (all rows identical)"; continue
        nulls = [dataset_level(permute_null(M, s), ks=(10,), seeds=(0,)) for s in range(3)]
        res[tag] = dict(
            null_knn10_drel_fixedbase=[n["knn10"]["drel_fixedbase"] for n in nulls],
            null_knn10_delta_fixedbase=[n["knn10"]["delta_fixedbase"] for n in nulls],
            null_knn10_diam=[n["knn10"]["diam"] for n in nulls],
            null_knn10_s=[n["knn10"]["s_sampled"] for n in nulls],
            null_euclid_drel=[n["euclid"]["drel_khrulkov"] for n in nulls])
    out[name] = res
    print(name, json.dumps(res, default=float)[:600], flush=True)
    json.dump(out, open(f"/tmp/claude-0/data/results_null{os.environ.get('TAG', '')}.json", "w"), indent=1, default=float)
print("DONE")
