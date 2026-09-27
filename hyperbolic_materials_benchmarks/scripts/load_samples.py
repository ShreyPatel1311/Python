"""Draw fixed-seed random samples from each accessible dataset into a common record format.

Record: dict(id, Z[int array], pos[(N,3)], cell[(3,3) or None], pbc[bool], chemsys[str],
             spg[int or None], bonds[(M,2) int array or None], targets[str])
"""
import glob, gzip, io, json, pickle, sys, tarfile, zipfile, urllib.request
import numpy as np, pandas as pd, pyarrow.parquet as pq, fsspec
from pymatgen.core import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

DATA = "/tmp/claude-0/data"
POOL = int(__import__("os").environ.get("POOL", 2000))
rng = np.random.default_rng(12345)
out = {}


def rec_from_struct(s, id_, targets, spg=None):
    if spg is None:
        try:
            spg = SpacegroupAnalyzer(s, symprec=0.1).get_space_group_number()
        except Exception:
            spg = None
    Z = np.array(s.atomic_numbers)
    return dict(id=id_, Z=Z, pos=s.cart_coords.copy(), cell=s.lattice.matrix.copy(), pbc=True,
                chemsys="-".join(sorted({e.symbol for e in s.composition.elements})), spg=spg, bonds=None,
                targets=targets)


def mp_parquet(path, name, targets, id_field):
    cols = ["atomic_numbers", "cart_coords", "cell", "chemsys", "symmetry", "provenance"]
    pf = pq.ParquetFile(path)
    prov = pf.read(columns=["provenance"]).column("provenance").combine_chunks()
    mids = np.array([m if m is not None else f"noid-{i}" for i, m in enumerate(prov.field(id_field).to_pylist())])
    uniq = np.unique(mids)
    pick_ids = rng.choice(uniq, size=min(POOL, len(uniq)), replace=False)
    # one random frame per picked material
    rows = []
    order = rng.permutation(len(mids))
    seen = set(); want = set(pick_ids)
    for r in order:
        m = mids[r]
        if m in want and m not in seen:
            seen.add(m); rows.append(r)
            if len(rows) == len(want):
                break
    rows = np.sort(np.array(rows))
    t = pf.read(columns=cols).take(rows).to_pydict()
    recs = []
    for i in range(len(rows)):
        recs.append(dict(id=f"{mids[rows[i]]}", Z=np.array(t["atomic_numbers"][i]),
                         pos=np.array(t["cart_coords"][i]), cell=np.array(t["cell"][i]), pbc=True,
                         chemsys=t["chemsys"][i], spg=(t["symmetry"][i] or {}).get("number"), bonds=None,
                         targets=targets))
    print(name, len(uniq), "unique materials;", len(recs), "sampled", flush=True)
    return recs


# 1-3) MLIP training sets with force/stress/magmom (MPtrj) or force/stress (MatPES, MP-ALOE) targets
import os
if os.path.exists(f"{DATA}/samples_part1.pkl"):
    out = pickle.load(open(f"{DATA}/samples_part1.pkl", "rb")); rng = np.random.default_rng(999)
else:
    out["MPtrj"] = mp_parquet(f"{DATA}/mptrj.parquet", "MPtrj", "E, forces (N,3), stress (3,3), magmoms", "material_id")
    out["MatPES-PBE"] = mp_parquet(f"{DATA}/matpes.parquet", "MatPES", "E, forces (N,3), stress (3,3)", "original_mp_id")
    out["MP-ALOE"] = mp_parquet(f"{DATA}/mpaloe.parquet", "MP-ALOE", "E, forces (N,3), stress (3,3)", "original_mp_id")
    pickle.dump(out, open(f"{DATA}/samples_part1.pkl", "wb"))

# 4) MP elasticity (structures included)
rows_ = pq.read_table(glob.glob(f"{DATA}/elasticity/*.parquet"), columns=["material_id", "structure", "symmetry", "deprecated"]).to_pylist()
seen_ = set(); t = []
for rw in rows_:
    if not rw["deprecated"] and rw["material_id"] not in seen_:
        seen_.add(rw["material_id"]); t.append(rw)
idx = rng.choice(len(t), size=min(POOL, len(t)), replace=False)
recs = []
for i in idx:
    row = t[i]
    st_ = row["structure"]
    s = Structure.from_dict(json.loads(st_) if isinstance(st_, str) else st_)
    recs.append(rec_from_struct(s, row["material_id"], "elastic tensor (rank 4)", (row["symmetry"] or {}).get("number")))
out["MP-elasticity"] = recs
print("MP-elasticity", len(t), "materials;", len(recs), "sampled", flush=True)

# 5-6) MP dielectric / piezoelectric: structures joined from MPtrj (lowest-energy/atom frame of same mp-id)
pf = pq.ParquetFile(f"{DATA}/mptrj.parquet")
base = pf.read(columns=["provenance", "energy", "nsites"]).to_pandas()
base["mid"] = base.provenance.map(lambda p: p["material_id"] if p else None)
base["epa"] = base.energy / base.nsites
base = base[base.mid.notna()]
best = base.sort_values("epa").drop_duplicates("mid").set_index("mid")
for coll, tg in [("dielectric", "dielectric tensor (rank 2)"), ("piezoelectric", "piezoelectric tensor (rank 3)")]:
    t = pq.read_table(glob.glob(f"{DATA}/{coll}/*.parquet"), columns=["material_id", "deprecated"]).to_pandas()
    t = t[~t.deprecated.astype(bool)].drop_duplicates("material_id")
    ids = [m for m in t.material_id if m in best.index]
    print(coll, len(t), "materials;", len(ids), "have an MPtrj structure", flush=True)
    pick = rng.choice(ids, size=min(POOL, len(ids)), replace=False)
    rowpos = base.reset_index().sort_values("epa").drop_duplicates("mid").set_index("mid").loc[pick, "index"].to_numpy()
    rowpos = np.sort(rowpos)
    tt = pf.read(columns=["atomic_numbers", "cart_coords", "cell", "chemsys", "symmetry", "provenance"]).take(rowpos).to_pydict()
    out[f"MP-{coll}"] = [dict(id=tt["provenance"][i]["material_id"], Z=np.array(tt["atomic_numbers"][i]),
                             pos=np.array(tt["cart_coords"][i]), cell=np.array(tt["cell"][i]), pbc=True,
                             chemsys=tt["chemsys"][i], spg=(tt["symmetry"][i] or {}).get("number"), bonds=None,
                             targets=tg) for i in range(len(rowpos))]
del base, best
pickle.dump(out, open(f"{DATA}/samples_part2.pkl", "wb"))

# 7-9) CDVAE generative benchmarks (target = the structure itself, E(3)/lattice-equivariant generation)
for s in ["mp_20", "perov_5", "carbon_24"]:
    df = pd.concat([pd.read_csv(f"{DATA}/{s}/{sp}.csv") for sp in ["train", "val", "test"]])
    idx = rng.choice(len(df), size=min(POOL, len(df)), replace=False)
    recs = []
    for i in idx:
        row = df.iloc[i]
        st = Structure.from_str(row.cif, fmt="cif")
        spg = int(row["spacegroup.number"]) if "spacegroup.number" in df.columns else None
        recs.append(rec_from_struct(st, str(row.material_id), "structure generation (coords, lattice)", spg))
    out[{"mp_20": "MP-20", "perov_5": "Perov-5", "carbon_24": "Carbon-24"}[s]] = recs
    print(s, len(df), "structures;", len(recs), "sampled", flush=True)
pickle.dump(out, open(f"{DATA}/samples_part3.pkl", "wb"))

# 10) GNoME (random CIFs from by_id.zip via HTTP range reads)
f = fsspec.open("https://storage.googleapis.com/gdm_materials_discovery/gnome_data/by_id.zip", block_size=2**16).open()
z = zipfile.ZipFile(f)
names = [n for n in z.namelist() if n.endswith(".CIF")]
pick = rng.choice(len(names), size=POOL, replace=False)
recs = []
for j, i in enumerate(pick):
    st = Structure.from_str(z.read(names[i]).decode(), fmt="cif")
    recs.append(rec_from_struct(st, names[i].split("/")[-1][:-4], "E (stability); structures"))
out["GNoME"] = recs
print("GNoME", len(names), "structures;", len(recs), "sampled", flush=True)
pickle.dump(out, open(f"{DATA}/samples_part4.pkl", "wb"))

# 11) QM9 (molecules with SDF bond tables)
from rdkit import Chem
tf = tarfile.open(f"{DATA}/gdb9.tar.gz"); sdf = tf.extractfile("gdb9.sdf").read()
suppl = Chem.ForwardSDMolSupplier(io.BytesIO(sdf), removeHs=False, sanitize=False)
mols = [m for m in suppl if m is not None]
pick = rng.choice(len(mols), size=POOL, replace=False)
recs = []
for i in pick:
    m = mols[i]
    Z = np.array([a.GetAtomicNum() for a in m.GetAtoms()])
    pos = m.GetConformer().GetPositions()
    bonds = np.array([[b.GetBeginAtomIdx(), b.GetEndAtomIdx()] for b in m.GetBonds()])
    recs.append(dict(id=m.GetProp("_Name"), Z=Z, pos=pos, cell=None, pbc=False,
                     chemsys="-".join(sorted({a.GetSymbol() for a in m.GetAtoms()})), spg=None, bonds=bonds,
                     targets="12 scalar targets incl. |mu| (invariant)"))
out["QM9"] = recs
print("QM9", len(mols), "molecules;", len(recs), "sampled", flush=True)

# 12) MP molecules (MPcules): first records streamed from several partitions; dipole vector target
B = "https://materialsproject-build.s3.amazonaws.com/collections/2025-09-25/molecules/"
parts = ["nelements=3/symmetry_point_group=C1.jsonl.gz", "nelements=4/symmetry_point_group=C1.jsonl.gz",
         "nelements=3/symmetry_point_group=Cs.jsonl.gz", "nelements=2/symmetry_point_group=C1.jsonl.gz"]
recs = []
for p in parts:
    with urllib.request.urlopen(B + p) as resp:
        g = gzip.GzipFile(fileobj=resp)
        for k, line in enumerate(g):
            if k >= POOL // len(parts):
                break
            d = json.loads(line)
            mol = d["molecules"]; key = next(iter(mol))
            sites = mol[key]["sites"]
            Z = np.array([__import__("pymatgen.core", fromlist=["Element"]).Element(s["species"][0]["element"]).Z for s in sites])
            pos = np.array([s["xyz"] for s in sites])
            recs.append(dict(id=d["molecule_id"], Z=Z, pos=pos, cell=None, pbc=False, chemsys=d["chemsys"], spg=None,
                             bonds=None, targets="dipole vector (rank 1), charges, thermo"))
out["MPcules"] = recs
print("MPcules", len(recs), "sampled (first records of 4 partitions)", flush=True)
pickle.dump(out, open(f"{DATA}/samples.pkl", "wb"))
print("DONE", {k: (len(v) if v else None) for k, v in out.items()})
