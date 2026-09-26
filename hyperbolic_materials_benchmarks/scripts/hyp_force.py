"""Energy + force regression with a distance-aware hyperbolic message-passing network and its Euclidean twin.

HYP: HGCN layers (Chami et al. 2019, arXiv:1910.12933; manifold code from HazyResearch/hgcn manifolds/poincare.py):
     HypLinear (Mobius mat-vec + Mobius bias) -> aggregation in the tangent space at the origin (HGCN local_agg=0)
     -> HypAct (log map at c_in, activation, exp map at c_out). Aggregation weights are continuous filters of the
     interatomic distance (SchNet cfconv, Schutt et al. 2017, arXiv:1706.08566): W(d_ij) = MLP(Bessel RBF(d_ij)) * cosine
     cutoff, Bessel basis as in DimeNet (Gasteiger et al. 2020, arXiv:2003.03123).
     One trainable curvature per layer boundary, c_l = softplus(rho_l), initialised at c = 1 (L+1 values).
EUC: identical code with exp/log maps = identity and Mobius ops = Euclidean ops (a SchNet-style GCN).
Energy E = sum_i [MLP(log_0(h_i)) * s + e0(Z_i)], s = training force RMS (NequIP default per-species scale), e0 = per-element least-squares fit on the training split
(the network is trained on E - e0, computed in float64).
Forces F = -dE/dx (autograd), so E is E(3)-invariant and F is E(3)-equivariant by construction.
Loss = [MSE(E/atom) + MSE(F)] / var(F) over all atoms, i.e. equal weights in eV/atom and eV/A (same as MACE
energy_weight = forces_weight = 1 up to a constant). OC20: free-atom force MAE also reported.

Displacement probe (hypothesis test): for up to 40 test structures, Gaussian displacements sigma in {0.01, 0.03, 0.1} A;
R(sigma) = mean over atoms of d(h_i(x), h_i(x+eps)) / median d(h_a, h_b) over random atom pairs of the unperturbed
test set, with d = Poincare distance at the last curvature (HYP) or Euclidean distance (EUC); h = last-layer node states.

Usage: hyp_force.py <dataset MP-ALOE|MatPES|MD22|OC20> <model HYP|EUC> <seed> <max_epochs> [n_structures=3000]
Env: DEVICE (cuda/cpu), DTYPE (32/64), OUT (output dir), HGCN (repo path), EXPORT_XYZ=1 writes MACE extxyz splits.
"""
import json, math, os, sys, time
import numpy as np, torch, torch.nn as nn, torch.nn.functional as Fn

sys.path.insert(0, os.environ.get("HGCN", "/tmp/claude-0/hgcn"))
from manifolds.poincare import PoincareBall

DATA = "/tmp/claude-0/data"
OUT = os.environ.get("OUT", DATA)
DS, MODEL, SEED, MAX_EP = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
N = int(sys.argv[5]) if len(sys.argv) > 5 else 3000
DEV = torch.device(os.environ.get("DEVICE", "cuda" if torch.cuda.is_available() else "cpu"))
DT = torch.float64 if os.environ.get("DTYPE", "32") == "64" else torch.float32
torch.set_default_dtype(DT)
RC, DIM, NL, NRBF, BS, PATIENCE = 5.0, 64, 3, 16, 16, 25
KCAL = 0.0433641


# ------------------------------------------------------------------ data (fixed sample: seed 7; fixed split: seed 123)
def load_raw():
    rng = np.random.default_rng(7)
    S = []
    if DS in ("MP-ALOE", "MatPES"):
        import pyarrow.parquet as pq
        pf = pq.ParquetFile(f"{DATA}/{'mpaloe' if DS == 'MP-ALOE' else 'matpes'}.parquet")
        rows = np.sort(rng.choice(pf.metadata.num_rows, size=N, replace=False))
        t = pf.read(columns=["atomic_numbers", "cart_coords", "cell", "energy", "forces"]).take(rows).to_pydict()
        for k in range(N):
            S.append(dict(Z=np.array(t["atomic_numbers"][k]), pos=np.array(t["cart_coords"][k]), cell=np.array(t["cell"][k]),
                          pbc=True, E=float(t["energy"][k]), F=np.array(t["forces"][k]), free=None))
    elif DS == "MD22":
        d = np.load(f"{DATA}/md22_Ac-Ala3-NHMe.npz")
        z, R, E_, F_ = d["z"], d["R"], d["E"], d["F"]   # NpzFile re-reads an array on every key access
        for k in np.sort(rng.choice(len(R), size=N, replace=False)):
            S.append(dict(Z=z, pos=R[k].copy(), cell=np.zeros((3, 3)), pbc=False, E=float(E_[k, 0]) * KCAL,
                          F=F_[k] * KCAL, free=None))
    elif DS == "OC20":
        import io, lzma, tarfile
        from ase.io import read
        tf = tarfile.open(f"{DATA}/s2ef_train_200K.tar")
        names = sorted([m for m in tf.getnames() if m.endswith(".extxyz.xz")])
        for fi in rng.choice(len(names), size=3, replace=False):
            fr = read(io.StringIO(lzma.decompress(tf.extractfile(names[fi]).read()).decode()), index=":", format="extxyz")
            meta = lzma.decompress(tf.extractfile(names[fi].replace(".extxyz.xz", ".txt.xz")).read()).decode().split()
            for k in rng.choice(len(fr), size=N // 3 + (1 if len(S) + N // 3 < N and fi == 0 else 0), replace=False):
                a = fr[k]; free = np.ones(len(a), bool)
                for c in a.constraints:
                    free[c.get_indices()] = False
                S.append(dict(Z=a.numbers.copy(), pos=a.positions.copy(), cell=np.array(a.cell), pbc=True,
                              E=float(a.get_potential_energy()) - float(meta[k].split(",")[2]),
                              F=a.get_forces(apply_constraint=False).copy(), free=free))
        S = S[:N]
    else:
        raise SystemExit(f"unknown dataset {DS}")
    return S


def build_graphs(S):
    from ase import Atoms
    from ase.neighborlist import neighbor_list
    for s in S:
        a = Atoms(numbers=s["Z"], positions=s["pos"], cell=s["cell"], pbc=s["pbc"])
        i, j, sh = neighbor_list("ijS", a, RC)
        s["ei"], s["ej"], s["sh"] = i, j, sh.astype(float)
    return S


cache = f"{DATA}/hf_{DS}_{N}.pt"
if os.path.exists(cache):
    S = torch.load(cache, weights_only=False)
else:
    S = build_graphs(load_raw()); torch.save(S, cache)
G = len(S)
perm = np.random.default_rng(123).permutation(G)
tr, va, te = perm[: int(.8 * G)], perm[int(.8 * G): int(.9 * G)], perm[int(.9 * G):]

if os.environ.get("EXPORT_XYZ") == "1":   # identical splits for the MACE baseline
    from ase import Atoms
    from ase.io import write
    for nm, idx in (("train", tr), ("valid", va), ("test", te)):
        ats = []
        for g in idx:
            s = S[g]; a = Atoms(numbers=s["Z"], positions=s["pos"], cell=s["cell"], pbc=s["pbc"])
            a.info["REF_energy"] = s["E"]; a.arrays["REF_forces"] = s["F"]
            if s["free"] is not None:
                a.arrays["free"] = s["free"].astype(int)
            ats.append(a)
        write(f"{OUT}/mace_{DS}_{N}_{nm}.xyz", ats, format="extxyz")
    print("exported extxyz splits", flush=True)
    sys.exit(0)

ZMAX = 100
comp = np.zeros((G, ZMAX))
for g in range(G):
    np.add.at(comp[g], S[g]["Z"], 1.0)
e0, *_ = np.linalg.lstsq(comp[tr], np.array([S[g]["E"] for g in tr]), rcond=None)
resid = np.array([(S[g]["E"] - comp[g] @ e0) / len(S[g]["Z"]) for g in tr])
E_SD = float(resid.std()) or 1.0
F_SD = float(np.concatenate([S[g]["F"].ravel() for g in tr]).std())
OUT_SCALE = float(np.sqrt(np.mean(np.concatenate([S[g]["F"].ravel() for g in tr]) ** 2)))  # force RMS (x 1 A)
AVG_NB = float(np.mean([len(S[g]["ei"]) / len(S[g]["Z"]) for g in tr]))


def batch(idx):
    Z, P, C, EI, EJ, SH, GI, E, F, FR, NA, off = [], [], [], [], [], [], [], [], [], [], [], 0
    for k, g in enumerate(idx):
        s = S[g]; n = len(s["Z"])
        Z.append(s["Z"]); P.append(s["pos"]); C.append(s["cell"]); EI.append(s["ei"] + off); EJ.append(s["ej"] + off)
        SH.append(s["sh"]); GI.append(np.full(len(s["ei"]), k)); E.append(s["E"]); F.append(s["F"])
        FR.append(s["free"] if s["free"] is not None else np.ones(n, bool)); NA.append(n); off += n
    t = lambda x, dt=DT: torch.as_tensor(np.concatenate(x) if isinstance(x, list) else x, dtype=dt, device=DEV)
    return dict(Z=t(Z, torch.long), pos=t(P), cell=torch.as_tensor(np.stack(C), dtype=DT, device=DEV),
                ei=t(EI, torch.long), ej=t(EJ, torch.long), sh=t(SH), egraph=t(GI, torch.long),
                batch=torch.repeat_interleave(torch.arange(len(idx), device=DEV), torch.as_tensor(NA, device=DEV)),
                # target = E - e0(composition), subtracted in float64 so float32 training keeps meV resolution
                E=t(np.array(E) - np.array([comp[g] @ e0 for g in idx])), F=t(F), free=t(FR, torch.bool),
                na=torch.as_tensor(NA, dtype=DT, device=DEV))


# ------------------------------------------------------------------ model
MAN = PoincareBall()


class Bessel(nn.Module):
    def __init__(self, n, rc):
        super().__init__()
        self.register_buffer("f", torch.arange(1, n + 1) * math.pi / rc); self.rc = rc
    def forward(self, d):
        d = d.unsqueeze(-1)
        return math.sqrt(2 / self.rc) * torch.sin(self.f * d) / d


class Layer(nn.Module):
    def __init__(self, hyp):
        super().__init__()
        self.hyp = hyp
        self.W = nn.Parameter(torch.empty(DIM, DIM)); nn.init.xavier_uniform_(self.W, gain=math.sqrt(2))
        self.b = nn.Parameter(torch.zeros(DIM))
        self.filt = nn.Sequential(nn.Linear(NRBF, DIM), nn.SiLU(), nn.Linear(DIM, DIM))

    def forward(self, h, c_in, c_out, ei, ej, rbf, env):
        if self.hyp:   # HypLinear
            h = MAN.proj(MAN.mobius_matvec(self.W, h, c_in), c_in)
            b = MAN.proj(MAN.expmap0(MAN.proj_tan0(self.b.view(1, -1), c_in), c_in), c_in)
            u = MAN.logmap0(MAN.proj(MAN.mobius_add(h, b, c_in), c_in), c_in)
        else:
            u = h @ self.W.T + self.b
        msg = self.filt(rbf) * env.unsqueeze(-1) * u[ej]                     # HypAgg with distance filter, tangent space
        u = u + torch.zeros_like(u).index_add_(0, ei, msg) / AVG_NB
        u = Fn.silu(u)                                                        # HypAct
        return MAN.proj(MAN.expmap0(MAN.proj_tan0(u, c_out), c_out), c_out) if self.hyp else u


class Net(nn.Module):
    def __init__(self, hyp):
        super().__init__()
        self.hyp = hyp
        self.emb = nn.Embedding(ZMAX, DIM)
        self.rbf = Bessel(NRBF, RC)
        self.layers = nn.ModuleList([Layer(hyp) for _ in range(NL)])
        # rho such that softplus(rho) = 1
        self.rho = nn.Parameter(torch.full((NL + 1,), math.log(math.e - 1))) if hyp else None
        self.head = nn.Sequential(nn.Linear(DIM, DIM), nn.SiLU(), nn.Linear(DIM, 1))

    def curv(self):
        return Fn.softplus(self.rho) if self.hyp else None

    def embed(self, b, pos):
        vec = pos[b["ej"]] - pos[b["ei"]] + torch.einsum("ek,ekl->el", b["sh"], b["cell"][b["egraph"]])
        d = vec.norm(dim=-1)
        env = 0.5 * (torch.cos(math.pi * d / RC) + 1) * (d < RC)
        rbf = self.rbf(d)
        c = self.curv()
        h = self.emb(b["Z"])
        if self.hyp:
            h = MAN.proj(MAN.expmap0(MAN.proj_tan0(h, c[0]), c[0]), c[0])
        for l, L in enumerate(self.layers):
            h = L(h, c[l] if self.hyp else None, c[l + 1] if self.hyp else None, b["ei"], b["ej"], rbf, env)
        return h

    def forward(self, b, forces=True, create_graph=False):
        pos = b["pos"].clone().requires_grad_(forces)
        h = self.embed(b, pos)
        u = MAN.logmap0(h, self.curv()[-1]) if self.hyp else h
        ea = self.head(u).squeeze(-1) * OUT_SCALE
        E = torch.zeros(len(b["na"]), device=DEV, dtype=DT).index_add_(0, b["batch"], ea)   # residual w.r.t. e0
        F = -torch.autograd.grad(E.sum(), pos, create_graph=create_graph)[0] if forces else None
        return E, F


torch.manual_seed(SEED); np.random.seed(SEED)
net = Net(MODEL == "HYP").to(DEV)
opt = torch.optim.Adam(net.parameters(), lr=1e-3)
sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, factor=0.5, patience=8)
n_par = sum(p.numel() for p in net.parameters())


def evaluate(idx):
    net.eval(); ae, af, aff, n_f, n_ff, loss = 0.0, 0.0, 0.0, 0, 0, 0.0
    for i in range(0, len(idx), BS):
        b = batch(idx[i:i + BS])
        E, F = net(b)
        E, F = E.detach(), F.detach()
        ae += float(((E - b["E"]).abs() / b["na"]).sum())
        loss += (float((((E - b["E"]) / b["na"]) ** 2).sum()) + float(((F - b["F"]) ** 2).mean()) * len(b["na"])) / F_SD ** 2
        af += float((F - b["F"]).abs().sum()); n_f += F.numel()
        aff += float((F - b["F"])[b["free"]].abs().sum()); n_ff += int(b["free"].sum()) * 3
    return dict(E_MAE_per_atom=ae / len(idx), F_MAE=af / n_f, F_MAE_free=aff / max(n_ff, 1), loss=loss / len(idx))


best, best_state, best_ep, bad, t0, diverged, log = 1e18, None, 0, 0, time.time(), False, []
for ep in range(MAX_EP):
    net.train(); p = np.random.permutation(tr)
    for i in range(0, len(p), BS):
        b = batch(p[i:i + BS])
        E, F = net(b, create_graph=True)
        loss = ((((E - b["E"]) / b["na"]) ** 2).mean() + ((F - b["F"]) ** 2).mean()) / F_SD ** 2
        if not torch.isfinite(loss):
            diverged = True; break
        opt.zero_grad(); loss.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 10.0); opt.step()
    if diverged:
        break
    v = evaluate(va); sched.step(v["loss"])
    rec = dict(ep=ep + 1, val_loss=round(v["loss"], 5), val_E=round(v["E_MAE_per_atom"], 5), val_F=round(v["F_MAE"], 5),
               lr=opt.param_groups[0]["lr"])
    if net.hyp:
        rec["c"] = [round(float(x), 4) for x in net.curv().detach()]
    log.append(rec)
    if not math.isfinite(v["loss"]):
        diverged = True; break
    if v["loss"] < best:
        best, best_ep, bad = v["loss"], ep + 1, 0
        best_state = {k: t.detach().clone() for k, t in net.state_dict().items()}
    else:
        bad += 1
        if bad >= PATIENCE or opt.param_groups[0]["lr"] < 1e-5:
            break
    if ep % 10 == 0:
        print(json.dumps(rec), flush=True)
train_sec = time.time() - t0
if best_state is not None:
    net.load_state_dict(best_state)
test = evaluate(te) if best_state is not None else None


# ------------------------------------------------------------------ displacement probe
def embed_dist(a, b_):
    if net.hyp:
        c = net.curv()[-1]
        return 2 / c.sqrt() * torch.atanh((c.sqrt() * MAN.mobius_add(-a, b_, c).norm(dim=-1)).clamp(max=1 - 1e-7))
    return (a - b_).norm(dim=-1)


probe = {}
if best_state is not None:
    net.eval(); g = torch.Generator(device="cpu").manual_seed(0)
    pidx = te[:40]
    b = batch(pidx)
    with torch.no_grad():
        h0 = net.embed(b, b["pos"])
        ia = torch.randint(0, len(h0), (20000,), generator=g).to(DEV); ib = torch.randint(0, len(h0), (20000,), generator=g).to(DEV)
        scale = float(embed_dist(h0[ia], h0[ib]).median())
        E0 = net(b, forces=False)[0]
        for sig in (0.01, 0.03, 0.1):
            eps = (torch.randn(b["pos"].shape, generator=g) * sig).to(DEV, DT)
            h1 = net.embed(b, b["pos"] + eps)
            E1 = net(dict(b, pos=b["pos"] + eps), forces=False)[0]
            dh = embed_dist(h0, h1)
            probe[str(sig)] = dict(R_mean=float(dh.mean()) / scale, R_median=float(dh.median()) / scale,
                                   dE_per_atom_mean=float(((E1 - E0).abs() / b["na"]).mean()))
        probe["pair_median_dist"] = scale

res = dict(dataset=DS, model=MODEL, seed=SEED, n_structures=G, n_train=len(tr), n_params=n_par, dtype=str(DT),
           device=str(DEV), epochs_run=len(log), best_epoch=best_ep, diverged=diverged, train_sec=round(train_sec, 1),
           sec_per_epoch=round(train_sec / max(len(log), 1), 2), test=test, E_SD=E_SD, F_SD=F_SD, out_scale=OUT_SCALE, avg_neighbors=AVG_NB,
           curvature_final=[float(x) for x in net.curv().detach()] if net.hyp else None, probe=probe, curve=log)
print("RESULT " + json.dumps({k: v for k, v in res.items() if k != "curve"}), flush=True)
json.dump(res, open(f"{OUT}/hf_{DS}_{MODEL}_s{SEED}_n{G}.json", "w"))
