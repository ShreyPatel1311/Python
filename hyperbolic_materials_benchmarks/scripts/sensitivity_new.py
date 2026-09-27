"""Force magnitudes and displacement sensitivity for samples_new.pkl (load_samples_new.py), same quantities as
sensitivity.py where the data allow:
  |F|    per-atom force magnitude (eV/A), free atoms only for OC20 (move_mask)
  pairs  molecules (MD22, rMD17): each sampled frame and the next frame in the file (same molecule);
         d = RMSD after optimal rotation/translation (Kabsch). Periodic (OMat24): records sharing parent_id, identical
         atom ordering and cell strain < 0.5%, nearest partner by min-image RMS displacement.
         OC20 S2EF 200K: README states every structure is from a different system, so no pairs.
  S_E = |d(E/atom)| / d (eV/atom per A); S_F = RMS(dF) / d (eV/A^2); cliff = d < 0.05 A and |d(E/atom)| > 0.1 eV."""
import json, os, pickle
import numpy as np

S = pickle.load(open(os.environ.get("SAMPLES", "/tmp/claude-0/data/samples_new.pkl"), "rb"))
TAG = os.environ.get("TAG", "_new")


def kabsch_rmsd(P, Q):
    P = P - P.mean(0); Q = Q - Q.mean(0)
    U, s, Vt = np.linalg.svd(P.T @ Q)
    d = np.sign(np.linalg.det(U @ Vt))
    s[-1] *= d
    return float(np.sqrt(max((P ** 2).sum() + (Q ** 2).sum() - 2 * s.sum(), 0) / len(P)))


def mic_rms(a, b):
    L = a["cell"]
    f = np.linalg.solve(L.T, (b["pos"] - a["pos"]).T).T
    f -= np.round(f)
    return float(np.sqrt(((f @ L) ** 2).sum(1).mean()))


def q(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return {"n": int(len(x)), **({k: float(np.percentile(x, p)) for k, p in (("median", 50), ("p95", 95), ("p99", 99))} if len(x) else {})}


out = {}
for name, recs in S.items():
    if not recs or recs[0].get("F") is None:
        continue
    F = np.concatenate([np.linalg.norm(r["F"][r["move"]] if r.get("move") is not None else r["F"], axis=1) for r in recs])
    pairs = []
    if not recs[0]["pbc"]:
        byid = {r["id"]: r for r in recs}
        for r in recs:
            mol, i = r["id"].rsplit(":", 1)
            nb = byid.get(f"{mol}:{int(i) + 1}")
            if nb is not None:
                pairs.append((r, nb, kabsch_rmsd(r["pos"], nb["pos"])))
    elif not name.startswith("OC20"):
        groups = {}
        for r in recs:
            groups.setdefault(r["group"], []).append(r)
        for g in groups.values():
            for a in g:
                best = None
                for b in g:
                    if b is a or len(b["Z"]) != len(a["Z"]) or not np.array_equal(a["Z"], b["Z"]):
                        continue
                    if np.abs(np.linalg.solve(a["cell"], b["cell"]) - np.eye(3)).max() > 0.005:
                        continue
                    d = mic_rms(a, b)
                    if d > 1e-4 and (best is None or d < best[2]):
                        best = (a, b, d)
                if best:
                    pairs.append(best)
    res = dict(n_structures=len(recs), force_abs=q(F), n_pairs=len(pairs))
    if pairs:
        d = np.array([p[2] for p in pairs])
        dE = np.array([abs(p[1]["E"] / len(p[1]["Z"]) - p[0]["E"] / len(p[0]["Z"])) for p in pairs])
        dF = np.array([np.sqrt(((p[1]["F"] - p[0]["F"]) ** 2).sum(1).mean()) for p in pairs])
        small = d < 0.05
        res.update(d_rms=q(d), S_E=q(dE / d), S_F=q(dF / d), pairs_small_disp=int(small.sum()),
                   energy_cliffs_small_disp=int((dE[small] > 0.1).sum()))
    out[name] = res
    print(name, json.dumps(res), flush=True)
json.dump(out, open(f"/tmp/claude-0/data/sensitivity{TAG}.json", "w"), indent=1)
print("DONE")
