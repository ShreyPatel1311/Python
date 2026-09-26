"""Re-sample MP dielectric / piezoelectric with padded->unpadded MP ID normalisation
(verified: 7305/7332 dielectric IDs match MPtrj after stripping leading 'a' padding; chemsys agreement 100%)."""
import glob, pickle
import numpy as np, pyarrow.parquet as pq

DATA = "/tmp/claude-0/data"; POOL = 2000
rng = np.random.default_rng(2024)
norm = lambda m: "mp-" + (m[3:].lstrip("a") or "a") if m and m.startswith("mp-") else m
out = pickle.load(open(f"{DATA}/samples.pkl", "rb"))
pf = pq.ParquetFile(f"{DATA}/mptrj.parquet")
base = pf.read(columns=["provenance", "energy", "nsites"]).to_pandas()
base["mid"] = base.provenance.map(lambda p: p["material_id"] if p else None)
base = base[base.mid.notna()]
base["epa"] = base.energy / base.nsites
best = base.reset_index().sort_values("epa").drop_duplicates("mid").set_index("mid")  # column "index" = row position
for coll, tg in [("dielectric", "dielectric tensor (rank 2)"), ("piezoelectric", "piezoelectric tensor (rank 3)")]:
    t = pq.read_table(glob.glob(f"{DATA}/{coll}/*.parquet"), columns=["material_id", "deprecated"]).to_pandas()
    t = t[~t.deprecated.astype(bool)].drop_duplicates("material_id")
    ids = sorted({norm(m) for m in t.material_id} & set(best.index))
    print(coll, len(t), "materials;", len(ids), "matched to an MPtrj structure", flush=True)
    pick = rng.choice(ids, size=min(POOL, len(ids)), replace=False)
    rowpos = np.sort(best.loc[pick, "index"].to_numpy())
    tt = pf.read(columns=["atomic_numbers", "cart_coords", "cell", "chemsys", "symmetry", "provenance"]).take(rowpos).to_pydict()
    out[f"MP-{coll}"] = [dict(id=tt["provenance"][i]["material_id"], Z=np.array(tt["atomic_numbers"][i]),
                             pos=np.array(tt["cart_coords"][i]), cell=np.array(tt["cell"][i]), pbc=True,
                             chemsys=tt["chemsys"][i], spg=(tt["symmetry"][i] or {}).get("number"), bonds=None,
                             targets=tg) for i in range(len(rowpos))]
pickle.dump(out, open(f"{DATA}/samples.pkl", "wb"))
print({k: (len(v) if v else None) for k, v in out.items()})
