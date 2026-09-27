"""Per-atom electric-field-gradient (EFG) targets from JARVIS dft_3d (jdft_3d-9-24-2025.json, figshare file 64391379).

JARVIS stores `efg` as one row per symmetry-inequivalent site: [element, Wyckoff letter, 9 tensor components] (values as
stored; units not converted). Mapping to atoms: spglib (via pymatgen SpacegroupAnalyzer, symprec 0.1 then 0.01) gives
Wyckoff letters and equivalence classes (orbits); a structure is kept only if the (element, Wyckoff) pairs of its orbits
match the JARVIS rows one-to-one. Every atom of an orbit gets the row's tensor eigenvalues (rotation invariant, identical
within an orbit). The full tensor refers to one (unspecified) member of the orbit; `orbit` lets a loss take the best
member. Frame check: a tensor in the Cartesian frame of the stored lattice must satisfy R T R^T = T for the site-symmetry
rotations of its atom; the fraction of orbits (with non-trivial site symmetry) where some member satisfies this is printed,
and `frame_ok` marks structures where every checked orbit passes (used for full-tensor training).
Usage: efg_data.py [n_structures=3000]   -> /tmp/claude-0/data/efg_<n>.pkl
"""
import json, pickle, sys
import numpy as np
from pymatgen.core import Lattice, Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

D = "/tmp/claude-0/data"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
rng = np.random.default_rng(2026)
ok = lambda v: v not in (None, "na", "", [])
J = [x for x in json.load(open(f"{D}/jdft_3d-9-24-2025.json")) if ok(x.get("efg"))]
order = rng.permutation(len(J))


def site_rotations_cart(ds, L, i, frac):
    """Cartesian rotations of the space-group operations that map atom i onto itself (modulo lattice vectors)."""
    out = []
    for R, t in zip(ds.rotations, ds.translations):
        d = R @ frac[i] + t - frac[i]
        if np.abs(d - np.round(d)).max() < 1e-3:
            out.append(L.T @ R @ np.linalg.inv(L.T))   # lattice rows are vectors: x_cart = L^T f
    return out


recs, stats = [], dict(tried=0, mapped=0, orbits_checked=0, orbits_frame_ok=0)
for k in order:
    if len(recs) >= N:
        break
    x = J[k]; at = x["atoms"]; stats["tried"] += 1
    L = np.array(at["lattice_mat"], float); X = np.array(at["coords"], float)
    s = Structure(Lattice(L), at["elements"], X, coords_are_cartesian=at.get("cartesian", False))
    rows = {(r[0], r[1]): np.array(r[2:11], float).reshape(3, 3) for r in x["efg"]}
    if len(rows) != len(x["efg"]):
        continue
    for prec in (0.1, 0.01):
        try:
            ds = SpacegroupAnalyzer(s, symprec=prec).get_symmetry_dataset()
        except Exception:
            ds = None
        if ds is None:
            continue
        eq = np.asarray(ds.equivalent_atoms); wy = list(ds.wyckoffs)
        key = {o: (str(s[o].specie), wy[o]) for o in np.unique(eq)}
        if sorted(key.values()) == sorted(rows) and len(set(key.values())) == len(key):
            break
        ds = None
    if ds is None:
        continue
    stats["mapped"] += 1
    frac = s.frac_coords
    T = np.zeros((len(s), 3, 3)); ev = np.zeros((len(s), 3)); frame_ok = True
    for o, kv in key.items():
        t = rows[kv]; members = np.where(eq == o)[0]
        T[members] = t; ev[members] = np.sort(np.linalg.eigvalsh(0.5 * (t + t.T)))
        rots = site_rotations_cart(ds, L, members[0], frac)
        if len(rots) > 1 and np.abs(t).max() > 1e-6:
            stats["orbits_checked"] += 1
            good = False
            for m in members:
                Rs = site_rotations_cart(ds, L, m, frac)
                if max(np.abs(R @ t @ R.T - t).max() for R in Rs) < 0.05 * np.abs(t).max():
                    good = True; break
            stats["orbits_frame_ok"] += good; frame_ok &= good
    recs.append(dict(id=x["jid"], Z=np.array(s.atomic_numbers), pos=s.cart_coords.copy(), cell=L, pbc=True,
                     orbit=eq.copy(), T=T, eig=ev, spg=int(ds.number), frame_ok=bool(frame_ok)))
print(json.dumps(stats), "frame-consistent fraction:",
      round(stats["orbits_frame_ok"] / max(stats["orbits_checked"], 1), 4), flush=True)
pickle.dump(recs, open(f"{D}/efg_{N}.pkl", "wb"))
print("saved", len(recs), "structures,", sum(len(r["Z"]) for r in recs), "atoms;", sum(r["frame_ok"] for r in recs),
      "structures pass the frame check for every checked orbit", flush=True)
