"""Per-structure, rotation-invariant targets derived from tensor properties, for graph-level HGCN regression.

  MP-dielectric    : 3 eigenvalues (ascending) of `total` (3x3), MP 2025-09-25 build collection `dielectric`
  MP-piezoelectric : Frobenius norm of the rank-3 piezoelectric tensor from `total` (3x6 Voigt, C/m^2):
                     ||e||^2 = sum_i [sum_{a=1..3} e_ia^2 + 2 sum_{a=4..6} e_ia^2]   (e_ijk = e_ia, Voigt index a <-> jk)
  MP-elasticity    : bulk_modulus.voigt, shear_modulus.voigt (GPa; provided by the collection)
  JARVIS-elastic   : bulk_modulus_kv, shear_modulus_gv (GPa; these equal the Voigt averages of `elastic_tensor` within
                     0.5 GPa for 98.4 % / 98.9 % of dft_3d entries, checked in session 2)
  JARVIS-eps-optB88: (epsx + epsy + epsz) / 3 (one third of the trace of the OptB88vdW optical dielectric tensor)
  JARVIS DFPT piezo / dielectric: excluded -- dft_3d stores only `dfpt_piezo_max_*` scalars whose rotation invariance
  could not be verified from the data.
Structures: MP elasticity records carry their structure; MP dielectric / piezoelectric records do not, so the
lowest-energy/atom MPtrj frame of the same material is used (numeric IDs -> MPtrj alphabetical IDs with
emmet.core.mpid.AlphaID), kept only if nsites and chemsys agree with the collection record.
Output: /tmp/claude-0/data/tt_<name>.pkl, list of dict(id, Z, pos, cell, y). Usage: tensor_targets.py [n_per_dataset=1500]
"""
import gzip, io, json, os, re, sys, urllib.request, pickle
from concurrent.futures import ThreadPoolExecutor
import numpy as np

D = "/tmp/claude-0/data"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
B = "https://materialsproject-build.s3.amazonaws.com"
rng = np.random.default_rng(31)
ok = lambda v: v not in (None, "na", "", [])


def mp_collection(coll):
    s = urllib.request.urlopen(f"{B}/?list-type=2&prefix=collections/2025-09-25/{coll}/", timeout=120).read().decode()
    assert "<IsTruncated>false" in s
    keys = sorted(k for k in re.findall("<Key>([^<]*)", s) if k.endswith(".jsonl.gz") and "manifest" not in k)
    with ThreadPoolExecutor(16) as ex:
        blobs = list(ex.map(lambda k: urllib.request.urlopen(f"{B}/{k}", timeout=120).read(), keys))
    return [json.loads(l) for b in blobs for l in gzip.GzipFile(fileobj=io.BytesIO(b))]


def pick(recs):
    return [recs[i] for i in np.sort(rng.choice(len(recs), size=min(N, len(recs)), replace=False))]


def save(name, recs):
    pickle.dump(recs, open(f"{D}/tt_{name}.pkl", "wb"))
    y = np.array([r["y"] for r in recs])
    print(name, len(recs), "structures; target mean", np.round(y.mean(0), 4).tolist(), "sd", np.round(y.std(0), 4).tolist(), flush=True)


def piezo_norm(e):
    e = np.asarray(e, float)
    return float(np.sqrt((e[:, :3] ** 2).sum() + 2 * (e[:, 3:] ** 2).sum()))


# ---------------------------------------------------------------- MP elasticity (structures included)
from pymatgen.core import Structure
el = [d for d in mp_collection("elasticity") if not d.get("deprecated") and d.get("structure")
      and ok((d.get("bulk_modulus") or {}).get("voigt")) and ok((d.get("shear_modulus") or {}).get("voigt"))]
el = list({d["material_id"]: d for d in el}.values())
recs = []
for d in pick(el):
    s = Structure.from_dict(d["structure"])
    recs.append(dict(id=d["material_id"], Z=np.array(s.atomic_numbers), pos=s.cart_coords.copy(), cell=s.lattice.matrix.copy(),
                     y=[float(d["bulk_modulus"]["voigt"]), float(d["shear_modulus"]["voigt"])]))
save("MP-elasticity", recs)

# ---------------------------------------------------------------- MP dielectric / piezoelectric (MPtrj structures)
import pyarrow.parquet as pq
from emmet.core.mpid import AlphaID
norm = lambda m: "mp-" + AlphaID(int(m[3:]))._identifier if m[3:].isdigit() else "mp-" + (m[3:].lstrip("a") or "a")
pf = pq.ParquetFile(f"{D}/mptrj.parquet")
base = pf.read(columns=["provenance", "energy", "nsites", "chemsys"]).to_pandas()
base["mid"] = base.provenance.map(lambda p: p["material_id"] if p else None)
base = base[base.mid.notna()]; base["epa"] = base.energy / base.nsites
best = base.reset_index().sort_values("epa").drop_duplicates("mid").set_index("mid")
for coll, name, f in [("dielectric", "MP-dielectric", lambda d: np.sort(np.linalg.eigvalsh(np.asarray(d["total"], float))).tolist()),
                      ("piezoelectric", "MP-piezoelectric", lambda d: [piezo_norm(d["total"])])]:
    C = [d for d in mp_collection(coll) if not d.get("deprecated") and ok(d.get("total"))]
    C = list({d["material_id"]: d for d in C}.values())
    match = [d for d in C if norm(d["material_id"]) in best.index
             and best.loc[norm(d["material_id"]), "nsites"] == d["nsites"] and best.loc[norm(d["material_id"]), "chemsys"] == d["chemsys"]]
    print(coll, len(C), "records;", len(match), "with an MPtrj frame of equal nsites and chemsys", flush=True)
    P = pick(match)
    rows = np.array([best.loc[norm(d["material_id"]), "index"] for d in P])
    order = np.argsort(rows)
    t = pf.read(columns=["atomic_numbers", "cart_coords", "cell"]).take(rows[order]).to_pydict()
    recs = [None] * len(P)
    for k, o in enumerate(order):
        recs[o] = dict(id=P[o]["material_id"], Z=np.array(t["atomic_numbers"][k]), pos=np.array(t["cart_coords"][k]),
                       cell=np.array(t["cell"][k]), y=f(P[o]))
    save(name, recs)
del base, best

# ---------------------------------------------------------------- JARVIS dft_3d
from ase.data import atomic_numbers
J = json.load(open(f"{D}/jdft_3d-9-24-2025.json"))


def jrec(r, y):
    at = r["atoms"]; L = np.array(at["lattice_mat"], float); X = np.array(at["coords"], float)
    return dict(id=r["jid"], Z=np.array([atomic_numbers[e] for e in at["elements"]]), cell=L,
                pos=X if at.get("cartesian", False) else X @ L, y=y)


fin = lambda *v: all(ok(x) and np.isfinite(float(x)) for x in v)
save("JARVIS-elastic", [jrec(r, [float(r["bulk_modulus_kv"]), float(r["shear_modulus_gv"])])
                        for r in pick([r for r in J if fin(r.get("bulk_modulus_kv"), r.get("shear_modulus_gv"))])])
save("JARVIS-eps-optB88", [jrec(r, [(float(r["epsx"]) + float(r["epsy"]) + float(r["epsz"])) / 3])
                           for r in pick([r for r in J if fin(r.get("epsx"), r.get("epsy"), r.get("epsz"))])])
print("DONE")
