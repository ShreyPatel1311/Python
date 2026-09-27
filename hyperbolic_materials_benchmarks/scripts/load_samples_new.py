"""Fixed-seed samples of datasets whose hosts were blocked in the first session, in the load_samples.py record format
plus energies / forces where the dataset has them (E in eV, F in eV/A; kcal/mol converted with 1 kcal/mol = 0.0433641 eV).

  MD22   (sgdml.org; npz: R, z, E, F; e_unit kcal/mol, r_unit Ang per file metadata) - 7 molecules, frames pooled
  rMD17  (figshare 12672038; README: coords A, energies kcal/mol, forces kcal/mol/A) - 10 molecules, frames pooled
  OC20   S2EF 200K train split (dl.fbaipublicfiles.com; extxyz + txt: system_id, frame_number, reference_energy)
  OMat24 val rattled-300-subsampled and aimd-from-PBE-3000-nvt (aselmdb; read with ase-db-backends)
  JARVIS dft_3d (figshare file 64391379, jdft_3d-9-24-2025.json): entries with elastic tensor / DFPT piezo / DFPT dielectric

Record keys: id, Z, pos, cell, pbc, chemsys, spg, bonds, targets, group (same molecule / same parent system), E, F,
move (OC20: free-atom mask). Molecule ids are '<molecule>:<rank>' with rank in file order (MD22) or original-MD17
index order (rMD17), so ids with consecutive ranks are neighbouring frames.
Usage: load_samples_new.py [pool=2000]
"""
import glob, json, lzma, os, pickle, sys, tarfile
import numpy as np

DATA = "/tmp/claude-0/data"
POOL = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
KCAL = 0.0433641
rng = np.random.default_rng(2026)
out = {}
SYM = None


def chemsys(Z):
    global SYM
    if SYM is None:
        from ase.data import chemical_symbols as SYM
    return "-".join(sorted({SYM[z] for z in Z}))


def mol_rec(id_, Z, R, E, F, group, targets):
    return dict(id=id_, Z=np.asarray(Z, int), pos=np.asarray(R, float), cell=None, pbc=False, chemsys=chemsys(Z), spg=None,
                bonds=None, targets=targets, group=group, E=float(E), F=np.asarray(F, float), move=None)


def molecules(files, name, loader, targets):
    """Equal share of POOL per molecule; frames kept in file order (neighbouring indices used for sensitivity)."""
    recs = []
    per = POOL // len(files)
    for f in files:
        Z, R, E, F, mol, order = loader(f)
        # order: frame order used for neighbour pairs (file order for MD22; original MD17 index for rMD17)
        k = np.sort(rng.choice(len(R) - 1, size=min(per // 2, len(R) - 1), replace=False))
        k = np.unique(np.concatenate([k, k + 1]))  # each pick plus the next frame in that order
        for j in k:
            i = order[j]
            recs.append(mol_rec(f"{mol}:{j}", Z, R[i], E[i], F[i], mol, targets))
        print(name, mol, len(R), "frames;", len(k), "sampled", flush=True)
    return recs


def md22(f):
    d = np.load(f)
    return d["z"], d["R"], d["E"].ravel() * KCAL, d["F"] * KCAL, str(d["name"]), np.arange(len(d["R"]))


def rmd17(f):
    d = np.load(f)
    return (d["nuclear_charges"], d["coords"], d["energies"] * KCAL, d["forces"] * KCAL, os.path.basename(f)[6:-4],
            np.argsort(d["old_indices"], kind="stable"))


f22 = sorted(glob.glob(f"{DATA}/md22_*.npz"))
if f22:
    out["MD22"] = molecules(f22, "MD22", md22, "E, forces (N,3)")
f17 = sorted(glob.glob(f"{DATA}/rmd17_*.npz"))
if f17:
    out["rMD17"] = molecules(f17, "rMD17", rmd17, "E, forces (N,3)")

# ---------------------------------------------------------------- OC20 S2EF 200K
tf_path = f"{DATA}/s2ef_train_200K.tar"
if os.path.exists(tf_path):
    from ase.io import read
    import io
    tf = tarfile.open(tf_path)
    xyz = sorted([m for m in tf.getnames() if m.endswith(".extxyz.xz")], key=lambda s: int(s.split("/")[-1].split(".")[0]))
    pick_files = rng.choice(len(xyz), size=min(4, len(xyz)), replace=False)
    recs = []
    for fi in pick_files:
        frames = read(io.StringIO(lzma.decompress(tf.extractfile(xyz[fi]).read()).decode()), index=":", format="extxyz")
        meta = lzma.decompress(tf.extractfile(xyz[fi].replace(".extxyz.xz", ".txt.xz")).read()).decode().split()
        for i in rng.choice(len(frames), size=POOL // len(pick_files), replace=False):
            a = frames[i]; sid, fr, eref = meta[i].split(",")
            # ASE turns the extxyz move_mask into FixAtoms and zeroes those forces unless apply_constraint=False
            mm = np.ones(len(a), bool)
            for c in a.constraints:
                mm[c.get_indices()] = False
            recs.append(dict(id=f"{sid}:{fr}", Z=a.numbers.copy(), pos=a.positions.copy(), cell=np.array(a.cell), pbc=True,
                             chemsys=chemsys(a.numbers), spg=None, bonds=None,
                             targets="E (adsorption, referenced), forces (N,3)", group=sid,
                             E=float(a.get_potential_energy()) - float(eref), F=a.get_forces(apply_constraint=False).copy(),
                             move=mm))
    out["OC20-S2EF"] = recs
    print("OC20-S2EF", len(recs), "sampled from files", sorted(pick_files.tolist()), flush=True)

# ---------------------------------------------------------------- OMat24 validation subsets
from ase.db import connect
for sub in ["rattled-300-subsampled", "aimd-from-PBE-3000-nvt"]:
    p = f"{DATA}/{sub}/data.aselmdb"
    if not os.path.exists(p):
        continue
    db = connect(p, type="aselmdb")
    n = db.count()
    recs = []
    for i in np.sort(rng.choice(n, size=min(POOL, n), replace=False)):
        row = db.get(int(i) + 1); a = row.toatoms(); dd = row.data or {}
        recs.append(dict(id=f"{dd.get('sid', i)}", Z=a.numbers.copy(), pos=a.positions.copy(), cell=np.array(a.cell), pbc=True,
                         chemsys=chemsys(a.numbers), spg=None, bonds=None, targets="E, forces (N,3), stress (3,3)",
                         group=str(dd.get("parent_id", dd.get("sid", i))), E=float(a.get_potential_energy()),
                         F=a.get_forces(apply_constraint=False).copy(), move=None))
    out[f"OMat24-{sub}"] = recs
    print("OMat24", sub, n, "rows;", len(recs), "sampled", flush=True)

# ---------------------------------------------------------------- JARVIS dft_3d tensor subsets
jp = f"{DATA}/jdft_3d-9-24-2025.json"
if os.path.exists(jp):
    J = json.load(open(jp))
    def ok(v):
        return v not in (None, "na", "", [])
    for key, name, tg in [("elastic_tensor", "JARVIS-elastic", "elastic tensor (rank 4)"),
                          ("dfpt_piezo_max_eij", "JARVIS-piezo", "piezoelectric tensor (rank 3)"),
                          ("dfpt_piezo_max_dielectric", "JARVIS-dielectric", "dielectric tensor (rank 2)")]:
        rows = [r for r in J if ok(r.get(key))]
        recs = []
        for i in rng.choice(len(rows), size=min(POOL, len(rows)), replace=False):
            r = rows[i]; at = r["atoms"]
            L = np.array(at["lattice_mat"], float); X = np.array(at["coords"], float)
            pos = X if at.get("cartesian", False) else X @ L
            from ase.data import atomic_numbers
            Z = np.array([atomic_numbers[e] for e in at["elements"]])
            recs.append(dict(id=r["jid"], Z=Z, pos=pos, cell=L, pbc=True, chemsys=chemsys(Z),
                             spg=int(r["spg_number"]) if ok(r.get("spg_number")) else None, bonds=None, targets=tg,
                             group=r["jid"], E=None, F=None, move=None))
        out[name] = recs
        print(name, len(rows), "entries with", key, ";", len(recs), "sampled", flush=True)
    del J

pickle.dump(out, open(f"{DATA}/samples_new.pkl", "wb"))
print("DONE", {k: len(v) for k, v in out.items()})
