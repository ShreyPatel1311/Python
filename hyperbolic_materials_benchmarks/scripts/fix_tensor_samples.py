"""Re-sample MP dielectric / piezoelectric with MP ID normalisation to the MPtrj format (unpadded alphabetical, e.g.
mp-bdgr): padded alphabetical IDs lose their leading 'a' padding (first session: 7305/7332 dielectric IDs matched,
chemsys agreement 100%); numeric IDs (mp-570778, as in the 2025-09-25 build collections) are converted with
emmet.core.mpid.AlphaID (570778 -> bgmja). Chemsys agreement of matched pairs is printed as a check."""
import glob, pickle
import numpy as np, pyarrow.parquet as pq

DATA = "/tmp/claude-0/data"; POOL = int(__import__("os").environ.get("POOL", 2000))
rng = np.random.default_rng(2024)
def norm(m):
    if not m or not m.startswith("mp-"):
        return m
    if m[3:].isdigit():
        from emmet.core.mpid import AlphaID
        return "mp-" + AlphaID(int(m[3:]))._identifier
    return "mp-" + (m[3:].lstrip("a") or "a")
out = pickle.load(open(f"{DATA}/samples.pkl", "rb"))
pf = pq.ParquetFile(f"{DATA}/mptrj.parquet")
base = pf.read(columns=["provenance", "energy", "nsites", "chemsys"]).to_pandas()
base["mid"] = base.provenance.map(lambda p: p["material_id"] if p else None)
base = base[base.mid.notna()]
base["epa"] = base.energy / base.nsites
best = base.reset_index().sort_values("epa").drop_duplicates("mid").set_index("mid")  # column "index" = row position
for coll, tg in [("dielectric", "dielectric tensor (rank 2)"), ("piezoelectric", "piezoelectric tensor (rank 3)")]:
    cols = ["material_id", "deprecated"] + (["chemsys"] if "chemsys" in pq.read_schema(glob.glob(f"{DATA}/{coll}/*.parquet")[0]).names else [])
    t = pq.read_table(glob.glob(f"{DATA}/{coll}/*.parquet"), columns=cols).to_pandas()
    t = t[~t.deprecated.astype(bool)].drop_duplicates("material_id")
    ids = sorted({norm(m) for m in t.material_id} & set(best.index))
    print(coll, len(t), "materials;", len(ids), "matched to an MPtrj structure", flush=True)
    if "chemsys" in t.columns and ids:
        cs = dict(zip(t.material_id.map(norm), t.chemsys))
        agree = np.mean([cs[i] == best.loc[i, "chemsys"] for i in ids])
        print(coll, "chemsys agreement of matched pairs:", round(float(agree), 4), flush=True)
    pick = rng.choice(ids, size=min(POOL, len(ids)), replace=False)
    rowpos = np.sort(best.loc[pick, "index"].to_numpy())
    tt = pf.read(columns=["atomic_numbers", "cart_coords", "cell", "chemsys", "symmetry", "provenance"]).take(rowpos).to_pydict()
    out[f"MP-{coll}"] = [dict(id=tt["provenance"][i]["material_id"], Z=np.array(tt["atomic_numbers"][i]),
                             pos=np.array(tt["cart_coords"][i]), cell=np.array(tt["cell"][i]), pbc=True,
                             chemsys=tt["chemsys"][i], spg=(tt["symmetry"][i] or {}).get("number"), bonds=None,
                             targets=tg) for i in range(len(rowpos))]
pickle.dump(out, open(f"{DATA}/samples.pkl", "wb"))
print({k: (len(v) if v else None) for k, v in out.items()})
