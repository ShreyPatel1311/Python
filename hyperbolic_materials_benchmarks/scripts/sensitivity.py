"""Output sensitivity to small atomic displacements, measured on consecutive frames of the same trajectory.
For each pair of consecutive frames with identical atom ordering and near-constant cell (strain < 0.5%):
  d_rms  = RMS minimum-image atomic displacement (A)
  S_E    = |d(E/atom)| / d_rms          (eV/atom per A)
  S_gap  = |d(bandgap)| / d_rms         (eV per A)
  S_mag  = |d(mean |magmom|)| / d_rms   (muB/atom per A)
"Cliff" = d_rms < 0.05 A and (|d gap| > 0.5 eV  or  |d mean|magmom|| > 0.5 muB/atom  or |dE/atom| > 0.1 eV).
Also per-atom force magnitudes |F| (first-order energy change per A of displacement of that atom).
Trajectory keys: MPtrj (task_id, calcs_reversed_index) ordered by ionic_step_index;
MatPES / MP-ALOE (original_mp_id, md_ensemble, md_temperature, md_pressure, mlip_name) ordered by md_step."""
import json, sys
import numpy as np, pyarrow.parquet as pq, pandas as pd

rng = np.random.default_rng(11)
N_TRAJ = 4000
out = {}


def pair_stats(df):
    rows = []
    for _, g in df.groupby("traj", sort=False):
        g = g.sort_values("step")
        recs = g.to_dict("records")
        for a, b in zip(recs[:-1], recs[1:]):
            if a["nsites"] != b["nsites"] or not np.array_equal(a["Z"], b["Z"]):
                continue
            L1, L2 = np.array(a["cell"]), np.array(b["cell"])
            strain = np.abs(np.linalg.solve(L1, L2) - np.eye(3)).max()
            if strain > 0.005:
                continue
            f1 = np.linalg.solve(L1.T, np.array(a["pos"]).T).T
            f2 = np.linalg.solve(L1.T, np.array(b["pos"]).T).T
            df_ = f2 - f1; df_ -= np.round(df_)
            d = np.sqrt(((df_ @ L1) ** 2).sum(1).mean())
            if d < 1e-4:
                continue
            dE = abs(b["E"] / b["nsites"] - a["E"] / a["nsites"])
            dg = abs(b["gap"] - a["gap"]) if a["gap"] is not None and b["gap"] is not None else np.nan
            ma = np.mean(np.abs(a["mag"])) if a["mag"] is not None else np.nan
            mb = np.mean(np.abs(b["mag"])) if b["mag"] is not None else np.nan
            rows.append((d, dE, dg, abs(mb - ma)))
    return np.array(rows, dtype=float)


def summarize(name, P, F):
    d, dE, dg, dm = P.T
    small = d < 0.05
    def q(x):
        x = x[np.isfinite(x)]
        return {"n": int(len(x)), **({k: float(np.percentile(x, p)) for k, p in (("median", 50), ("p95", 95), ("p99", 99))} if len(x) else {})}
    def frac(v, thr):
        v = v[small]; v = v[np.isfinite(v)]
        return {"n_valid": int(len(v)), "count": int((v > thr).sum()), "frac": float((v > thr).mean()) if len(v) else None}
    res = dict(pairs=int(len(P)), pairs_small_disp=int(small.sum()), d_rms=q(d),
               S_E=q(dE / d), S_gap=q(dg / d), S_mag=q(dm / d),
               cliffs_small_disp=dict(gap=frac(dg, 0.5), mag=frac(dm, 0.5), energy=frac(dE, 0.1)),
               force_abs=q(F))
    out[name] = res
    print(name, json.dumps(res), flush=True)


def load(path, key_fn, step_fn):
    pf = pq.ParquetFile(path)
    prov = pf.read(columns=["provenance"]).column(0).to_pylist()
    keys = np.array([key_fn(p) for p in prov], dtype=object)
    uk, inv, cnt = np.unique(keys.astype(str), return_inverse=True, return_counts=True)
    multi = np.where(cnt >= 2)[0]
    pick = set(rng.choice(multi, size=min(N_TRAJ, len(multi)), replace=False).tolist())
    rows = np.where(np.isin(inv, list(pick)))[0]
    cols = ["atomic_numbers", "cart_coords", "cell", "energy", "nsites", "bandgap", "magmoms", "forces"]
    t = pf.read(columns=cols).take(rows).to_pydict()
    df = pd.DataFrame(dict(traj=inv[rows], step=[step_fn(prov[r]) for r in rows], Z=[np.array(z) for z in t["atomic_numbers"]],
                           pos=t["cart_coords"], cell=t["cell"], E=t["energy"], nsites=t["nsites"], gap=t["bandgap"],
                           mag=t["magmoms"]))
    fr = rng.choice(len(rows), size=min(3000, len(rows)), replace=False)
    F = np.concatenate([np.linalg.norm(np.array(t["forces"][i]), axis=1) for i in fr])
    return df, F, int(len(uk)), int(len(multi))


specs = {
    "MPtrj": ("/tmp/claude-0/data/mptrj.parquet",
              lambda p: f"{p['task_id']}|{p['calcs_reversed_index']}" if p else None,
              lambda p: p["ionic_step_index"] if p else 0),
    "MatPES": ("/tmp/claude-0/data/matpes.parquet",
               lambda p: f"{p['original_mp_id']}|{p['md_ensemble']}|{p['md_temperature']}|{p['md_pressure']}|{p['mlip_name']}" if p else None,
               lambda p: p["md_step"] if p and p["md_step"] is not None else 0),
    "MP-ALOE": ("/tmp/claude-0/data/mpaloe.parquet",
                lambda p: f"{p['original_mp_id']}|{p['md_ensemble']}|{p['md_temperature']}|{p['md_pressure']}|{p['mlip_name']}" if p else None,
                lambda p: p["md_step"] if p and p["md_step"] is not None else 0),
}
for name, (path, kf, sf) in specs.items():
    df, F, n_traj, n_multi = load(path, kf, sf)
    print(name, "frames with bandgap:", int(df.gap.notna().sum()), "with magmoms:", int(df.mag.notna().sum()), "of", len(df), flush=True)
    P = pair_stats(df)
    print(name, "trajectories:", n_traj, "with>=2 frames:", n_multi, "sampled frames:", len(df), flush=True)
    if len(P):
        summarize(name, P, F)
    else:
        out[name] = dict(pairs=0, note="no consecutive same-ordering pairs", force_abs=None, n_traj=n_traj)
    out[name]["n_trajectories"] = n_traj; out[name]["n_traj_multi_frame"] = n_multi
    json.dump(out, open("/tmp/claude-0/data/sensitivity.json", "w"), indent=1)
print("DONE")
