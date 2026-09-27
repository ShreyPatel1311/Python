"""Full per-site electric-field-gradient tensors (JARVIS dft_3d, efg_data.py) with the distance-aware hyperbolic network of
hyp_force.py (HGCN-style Poincare layers, one trainable curvature per layer boundary, Euclidean twin EUC) and a rank-2
equivariant head:
    T_i = sum_{j in N(i)} w_ij (r_ij r_ij^T - I/3),   r_ij = unit vector i->j (periodic images within 5 A),
    w_ij = MLP([u_i, u_j, Bessel-RBF(d_ij)]) * cosine cutoff * s,   u = log_0(h_L) (tangent-space node states),
so T_i is symmetric, traceless and rotates as R T R^T (w_ij are invariant); checked numerically at start-up.
JARVIS gives one tensor per symmetry orbit, referring to one unspecified member: the loss and the tensor MAE use, per
orbit, the member with the smallest error (the other members' reference tensors are symmetry-rotated copies). Only
structures that pass efg_data.py's frame check (frame_ok) are used. Eigenvalue MAE (sorted) is member-independent.
Loss = mean over orbits of min-member MSE / var(T components). Displacement probe as in hyp_force.py.
Usage: hyp_efg.py <HYP|EUC> <seed> <max_epochs> [n_source_structures=1500]
"""
import json, math, os, pickle, sys, time
import numpy as np, torch, torch.nn as nn, torch.nn.functional as Fn

sys.path.insert(0, os.environ.get("HGCN", "/tmp/claude-0/hgcn"))
from manifolds.poincare import PoincareBall

D = "/tmp/claude-0/data"; OUT = os.environ.get("OUT", D)
MODEL, SEED, MAX_EP = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
NSRC = int(sys.argv[4]) if len(sys.argv) > 4 else 1500
DEV = torch.device(os.environ.get("DEVICE", "cuda" if torch.cuda.is_available() else "cpu"))
DT = torch.float32; torch.set_default_dtype(DT)
RC, DIM, NL, NRBF, BS, PATIENCE = 5.0, 64, 3, 16, 16, 25

cache = f"{D}/efgT_{NSRC}.pkl"
if os.path.exists(cache):
    S = pickle.load(open(cache, "rb"))
else:
    from ase import Atoms
    from ase.neighborlist import neighbor_list
    S = [r for r in pickle.load(open(f"{D}/efg_{NSRC}.pkl", "rb")) if r["frame_ok"]]
    for s in S:
        a = Atoms(numbers=s["Z"], positions=s["pos"], cell=s["cell"], pbc=True)
        i, j, sh = neighbor_list("ijS", a, RC)
        s["ei"], s["ej"], s["sh"] = i, j, sh.astype(float)
    pickle.dump(S, open(cache, "wb"))
G = len(S)
perm = np.random.default_rng(123).permutation(G)
tr, va, te = perm[: int(.8 * G)], perm[int(.8 * G): int(.9 * G)], perm[int(.9 * G):]
T_SD = float(np.concatenate([S[g]["T"].ravel() for g in tr]).std())
AVG_NB = float(np.mean([len(S[g]["ei"]) / len(S[g]["Z"]) for g in tr]))


def batch(idx, rot=None):
    Z, P, C, EI, EJ, SH, GI, TT, OR, off, ooff = [], [], [], [], [], [], [], [], [], 0, 0
    for k, g in enumerate(idx):
        s = S[g]; n = len(s["Z"])
        pos, cell, T = s["pos"], s["cell"], s["T"]
        if rot is not None:
            pos, cell, T = pos @ rot.T, cell @ rot.T, rot @ T @ rot.T
        Z.append(s["Z"]); P.append(pos); C.append(cell); EI.append(s["ei"] + off); EJ.append(s["ej"] + off)
        SH.append(s["sh"]); GI.append(np.full(len(s["ei"]), k)); TT.append(T)
        _, o = np.unique(s["orbit"], return_inverse=True); OR.append(o + ooff); ooff += o.max() + 1; off += n
    t = lambda x, dt=DT: torch.as_tensor(np.concatenate(x), dtype=dt, device=DEV)
    return dict(Z=t(Z, torch.long), pos=t(P), cell=torch.as_tensor(np.stack(C), dtype=DT, device=DEV),
                ei=t(EI, torch.long), ej=t(EJ, torch.long), sh=t(SH), egraph=t(GI, torch.long), T=t(TT),
                orbit=t(OR, torch.long), n_orbit=ooff)


MAN = PoincareBall()


class Bessel(nn.Module):
    def __init__(self, n, rc):
        super().__init__(); self.register_buffer("f", torch.arange(1, n + 1) * math.pi / rc); self.rc = rc
    def forward(self, d):
        d = d.unsqueeze(-1); return math.sqrt(2 / self.rc) * torch.sin(self.f * d) / d


class Layer(nn.Module):   # identical to hyp_force.py
    def __init__(self, hyp):
        super().__init__()
        self.hyp = hyp
        self.W = nn.Parameter(torch.empty(DIM, DIM)); nn.init.xavier_uniform_(self.W, gain=math.sqrt(2))
        self.b = nn.Parameter(torch.zeros(DIM))
        self.filt = nn.Sequential(nn.Linear(NRBF, DIM), nn.SiLU(), nn.Linear(DIM, DIM))
    def forward(self, h, c_in, c_out, ei, ej, rbf, env):
        if self.hyp:
            h = MAN.proj(MAN.mobius_matvec(self.W, h, c_in), c_in)
            b = MAN.proj(MAN.expmap0(MAN.proj_tan0(self.b.view(1, -1), c_in), c_in), c_in)
            u = MAN.logmap0(MAN.proj(MAN.mobius_add(h, b, c_in), c_in), c_in)
        else:
            u = h @ self.W.T + self.b
        msg = self.filt(rbf) * env.unsqueeze(-1) * u[ej]
        u = Fn.silu(u + torch.zeros_like(u).index_add_(0, ei, msg) / AVG_NB)
        return MAN.proj(MAN.expmap0(MAN.proj_tan0(u, c_out), c_out), c_out) if self.hyp else u


class Net(nn.Module):
    def __init__(self, hyp):
        super().__init__()
        self.hyp = hyp
        self.emb = nn.Embedding(100, DIM); self.rbf = Bessel(NRBF, RC)
        self.layers = nn.ModuleList([Layer(hyp) for _ in range(NL)])
        self.rho = nn.Parameter(torch.full((NL + 1,), math.log(math.e - 1))) if hyp else None
        self.w = nn.Sequential(nn.Linear(2 * DIM + NRBF, DIM), nn.SiLU(), nn.Linear(DIM, 1))
    def curv(self):
        return Fn.softplus(self.rho) if self.hyp else None
    def geom(self, b):
        vec = b["pos"][b["ej"]] - b["pos"][b["ei"]] + torch.einsum("ek,ekl->el", b["sh"], b["cell"][b["egraph"]])
        d = vec.norm(dim=-1)
        return vec / d.unsqueeze(-1), d, 0.5 * (torch.cos(math.pi * d / RC) + 1) * (d < RC), self.rbf(d)
    def embed(self, b):
        rhat, d, env, rbf = self.geom(b); c = self.curv(); h = self.emb(b["Z"])
        if self.hyp:
            h = MAN.proj(MAN.expmap0(MAN.proj_tan0(h, c[0]), c[0]), c[0])
        for l, L in enumerate(self.layers):
            h = L(h, c[l] if self.hyp else None, c[l + 1] if self.hyp else None, b["ei"], b["ej"], rbf, env)
        return h, rhat, env, rbf
    def forward(self, b):
        h, rhat, env, rbf = self.embed(b)
        u = MAN.logmap0(h, self.curv()[-1]) if self.hyp else h
        w = self.w(torch.cat([u[b["ei"]], u[b["ej"]], rbf], -1)).squeeze(-1) * env * T_SD
        outer = rhat.unsqueeze(-1) * rhat.unsqueeze(-2) - torch.eye(3, device=DEV) / 3
        return torch.zeros(len(b["Z"]), 3, 3, device=DEV).index_add_(0, b["ei"], w[:, None, None] * outer), h


def orbit_err(Tp, b):
    """per-atom MSE / MAE against the orbit reference, then the best member per orbit"""
    mse = ((Tp - b["T"]) ** 2).mean((1, 2)); mae = (Tp - b["T"]).abs().mean((1, 2))
    best = torch.full((b["n_orbit"],), float("inf"), device=DEV).scatter_reduce(0, b["orbit"], mse, "amin")
    is_best = mse <= best[b["orbit"]] + 1e-12
    mae_best = torch.zeros(b["n_orbit"], device=DEV).scatter_reduce(0, b["orbit"][is_best], mae[is_best], "amax", include_self=False)
    return best, mae_best


torch.manual_seed(SEED); np.random.seed(SEED)
net = Net(MODEL == "HYP").to(DEV)
# equivariance check: prediction on a rotated copy vs rotated prediction
with torch.no_grad():
    q, _ = np.linalg.qr(np.random.default_rng(1).normal(size=(3, 3)))
    b0, b1 = batch(tr[:4]), batch(tr[:4], rot=q)
    R = torch.as_tensor(q, dtype=DT, device=DEV)
    equiv_err = float((R @ net(b0)[0] @ R.T - net(b1)[0]).abs().max() / net(b0)[0].abs().max())
print("equivariance relative error", equiv_err, flush=True)
opt = torch.optim.Adam(net.parameters(), lr=1e-3)
sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, factor=0.5, patience=8)


def evaluate(idx):
    net.eval(); se, ae, eig, n_o, n_a = 0.0, 0.0, 0.0, 0, 0
    with torch.no_grad():
        for i in range(0, len(idx), BS):
            b = batch(idx[i:i + BS]); Tp = net(b)[0]
            best, mae_best = orbit_err(Tp, b)
            se += float(best.sum()); ae += float(mae_best.sum()); n_o += b["n_orbit"]
            ev_p = torch.linalg.eigvalsh(0.5 * (Tp + Tp.transpose(1, 2))); ev_r = torch.linalg.eigvalsh(b["T"])
            eig += float((ev_p - ev_r).abs().sum()); n_a += len(Tp) * 3
    return dict(loss=se / n_o / T_SD ** 2, T_MAE_best_member=ae / n_o, eig_MAE=eig / n_a)


best, best_state, best_ep, bad, t0, diverged, log = 1e18, None, 0, 0, time.time(), False, []
for ep in range(MAX_EP):
    net.train(); p = np.random.permutation(tr)
    for i in range(0, len(p), BS):
        b = batch(p[i:i + BS]); Tp = net(b)[0]
        loss = orbit_err(Tp, b)[0].mean() / T_SD ** 2
        if not torch.isfinite(loss):
            diverged = True; break
        opt.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(net.parameters(), 10.0); opt.step()
    if diverged:
        break
    v = evaluate(va); sched.step(v["loss"])
    rec = dict(ep=ep + 1, val_loss=round(v["loss"], 5), val_eig_MAE=round(v["eig_MAE"], 4))
    if net.hyp:
        rec["c"] = [round(float(x), 4) for x in net.curv().detach()]
    log.append(rec)
    if v["loss"] < best:
        best, best_ep, bad = v["loss"], ep + 1, 0; best_state = {k: t.detach().clone() for k, t in net.state_dict().items()}
    else:
        bad += 1
        if bad >= PATIENCE or opt.param_groups[0]["lr"] < 1e-5:
            break
train_sec = time.time() - t0
if best_state is not None:
    net.load_state_dict(best_state)
test = evaluate(te) if best_state is not None else None

probe = {}
if best_state is not None:   # displacement probe (as hyp_force.py)
    net.eval(); g = torch.Generator(device="cpu").manual_seed(0); b = batch(te[:40])
    def dist(a, c_):
        if net.hyp:
            c = net.curv()[-1]
            return 2 / c.sqrt() * torch.atanh((c.sqrt() * MAN.mobius_add(-a, c_, c).norm(dim=-1)).clamp(max=1 - 1e-7))
        return (a - c_).norm(dim=-1)
    with torch.no_grad():
        h0 = net.embed(b)[0]
        ia = torch.randint(0, len(h0), (20000,), generator=g).to(DEV); ib = torch.randint(0, len(h0), (20000,), generator=g).to(DEV)
        scale = float(dist(h0[ia], h0[ib]).median())
        for sig in (0.01, 0.03, 0.1):
            eps = (torch.randn(b["pos"].shape, generator=g) * sig).to(DEV, DT)
            probe[str(sig)] = dict(R_mean=float(dist(h0, net.embed(dict(b, pos=b["pos"] + eps))[0]).mean()) / scale)

n_par = sum(p.numel() for p in net.parameters())
res = dict(task="EFG-tensor", model=MODEL, seed=SEED, n_structures=G, n_params=n_par, equivariance_rel_err=equiv_err,
           T_SD=T_SD, epochs_run=len(log), best_epoch=best_ep, diverged=diverged, train_sec=round(train_sec, 1), test=test,
           curvature_final=[float(x) for x in net.curv().detach()] if net.hyp else None, probe=probe, curve=log)
print("RESULT " + json.dumps({k: v for k, v in res.items() if k != "curve"}), flush=True)
json.dump(res, open(f"{OUT}/efgT_{MODEL}_s{SEED}.json", "w"))
