"""HGCN (HazyResearch/hgcn) link prediction on our graphs, CPU, one seed.
Usage: hgcn_sweep.py <model: HGCN|GCN> <double: 0|1> <dataset|all> [out_tag]
Env FIX (divergence fixes, default none): "clip" = clip total grad norm to 1.0 before each step;
"clip+cbound" = clip and clamp every trainable curvature to [0.01, 100] after each step. Env SEEDS (default "0"), SAMPLES.
Each run records the curvatures (initial, final / last finite) and the gradient norm of the last finite step.
Graphs per dataset: MACE kNN10 graph (features = MACE invariant descriptors) and chemical-system inclusion graph
(features = element-membership vector; skipped when the dataset has a single chemical system).
Hyperparameters follow the repo README link-prediction examples (HGCN: airport; GCN: cora)."""
import itertools, json, os, pickle, sys, time
import numpy as np, scipy.sparse as sp, torch
sys.path.insert(0, "/tmp/claude-0/hgcn")
sys.path.insert(1, __file__.rsplit("/", 1)[0])
from config import parser
import optimizers
from models.base_models import LPModel
from utils.data_utils import mask_edges, process
from run_delta import knn_adj

torch.set_num_threads(4)
MODEL, DOUBLE, WHICH = sys.argv[1], int(sys.argv[2]), sys.argv[3]
FIX = os.environ.get("FIX", "none")
SEEDS = [int(x) for x in os.environ.get("SEEDS", "0").split(",")]
TAG = sys.argv[4] if len(sys.argv) > 4 else f"{MODEL}_d{DOUBLE}_{FIX}"
if DOUBLE:
    torch.set_default_dtype(torch.float64)   # same effect as the repo's --double-precision 1 (train.py)


def chemsys_graph(chemsyss):
    from pymatgen.core import Element
    nodes = set()
    for cs in chemsyss:
        els = tuple(sorted(cs.split("-")))
        for r in range(1, len(els) + 1):
            nodes.update(itertools.combinations(els, r))
    nodes = sorted(nodes); ix = {s: i for i, s in enumerate(nodes)}
    X = np.zeros((len(nodes), 119))
    for s, i in ix.items():
        for el in s:
            X[i, Element(el).Z] = 1
    e = np.array([(ix[s], ix[tuple(x for x in s if x != el)]) for s in nodes if len(s) > 1 for el in s])
    n = len(nodes)
    A = sp.csr_matrix((np.ones(2 * len(e)), (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])), shape=(n, n))
    A.data[:] = 1
    return A, X


def run(A, X, seed=0, normalize_feats=1):
    args = parser.parse_args([])
    args.task, args.model, args.dataset, args.seed, args.split_seed = "lp", MODEL, "custom", seed, seed
    args.manifold = "PoincareBall" if MODEL == "HGCN" else "Euclidean"
    args.c = None if MODEL == "HGCN" else 1.0
    args.dim, args.num_layers, args.lr, args.weight_decay, args.act, args.bias = 16, 2, 0.01, 0.0, "relu", 1
    args.dropout = 0.0 if MODEL == "HGCN" else 0.2
    args.normalize_feats = normalize_feats
    args.device = "cpu"; args.epochs = 5000; args.patience = 200; args.min_epochs = 500  # repo defaults 100/100 stopped GCN on a noisy epoch-2 peak; applied equally to all models
    np.random.seed(seed); torch.manual_seed(seed)
    adj_train, tr, trf, va, vaf, te, tef = mask_edges(A, args.val_prop, args.test_prop, seed)
    data = dict(adj_train=adj_train, train_edges=tr, train_edges_false=trf, val_edges=va, val_edges_false=vaf,
                test_edges=te, test_edges_false=tef)
    data["adj_train_norm"], data["features"] = process(adj_train, X, args.normalize_adj, args.normalize_feats)
    data["features"] = data["features"].to(torch.get_default_dtype())
    data["adj_train_norm"] = data["adj_train_norm"].to(torch.get_default_dtype())
    args.n_nodes, args.feat_dim = data["features"].shape
    args.nb_false_edges, args.nb_edges = len(trf), len(tr)
    args.lr_reduce_freq = args.epochs
    m = LPModel(args)
    opt = getattr(optimizers, args.optimizer)(params=m.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    best_val, best_test, best_epoch, best_emb, counter, t0 = m.init_metric_dict(), None, -1, None, 0, time.time()
    val_curve, diverged = [], False
    # encoder.curvatures = per-layer curvatures + model.c (HGCN encoder appends it); GCN has none
    curv = [p for p in getattr(m.encoder, "curvatures", []) if isinstance(p, torch.nn.Parameter) and p.requires_grad]
    c_init, c_last, gn_last = [float(p) for p in curv], None, None
    for epoch in range(args.epochs):
        m.train(); opt.zero_grad()
        emb = m.encode(data["features"], data["adj_train_norm"])
        loss = m.compute_metrics(emb, data, "train")["loss"]
        if not torch.isfinite(loss):
            diverged = True; break
        loss.backward()
        gn_last = float(torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0 if FIX.startswith("clip") else float("inf")))
        opt.step()
        if FIX == "clip+cbound":
            with torch.no_grad():
                for p in curv:
                    p.clamp_(0.01, 100.0)
        if not all(torch.isfinite(p).all() for p in curv):
            diverged = True; break
        c_last = [float(p) for p in curv]
        m.eval()
        with torch.no_grad():
            emb = m.encode(data["features"], data["adj_train_norm"])
            if not torch.isfinite(emb).all():
                diverged = True; break
            val = m.compute_metrics(emb, data, "val")
        val_curve.append(round(float(val["roc"]), 4))
        if m.has_improved(best_val, val):
            best_val, best_test, best_epoch, best_emb, counter = val, m.compute_metrics(emb, data, "test"), epoch + 1, emb.clone(), 0
        else:
            counter += 1
            if counter == args.patience and epoch > args.min_epochs:
                break
    sec = time.time() - t0
    return dict(model=MODEL, double=DOUBLE, fix=FIX, seed=seed, curv_init=c_init, curv_last_finite=c_last,
                grad_norm_last_finite_step=gn_last, epochs_run=epoch + 1, best_epoch=best_epoch, diverged=diverged,
                sec=round(sec, 2), sec_per_epoch=round(sec / (epoch + 1), 4),
                val_roc=float(best_val["roc"]) if best_test else None,
                test_roc=float(best_test["roc"]) if best_test else None,
                test_ap=float(best_test["ap"]) if best_test else None,
                n_nodes=int(A.shape[0]), n_edges=int(A.nnz // 2), val_curve=val_curve), best_emb


samples = pickle.load(open(os.environ.get("SAMPLES", "/tmp/claude-0/data/samples.pkl"), "rb"))
names = list(samples) if WHICH == "all" else [WHICH]
out, t_all = [], time.time()
for name in names:
    Xm = np.load(f"/tmp/claude-0/data/mace_{name}.npy")
    # MACE descriptors are signed (~50% negative); the repo's row-sum normalisation assumes non-negative features,
    # so standardise per column and disable it (README disease_lp example also uses --normalize-feats 0)
    Xs = (Xm - Xm.mean(0)) / np.where(Xm.std(0) > 0, Xm.std(0), 1.0)
    graphs = {"mace_knn10": (knn_adj(Xm, 10), Xs, 0)}
    cs = [r["chemsys"] for r in samples[name][:1000]]
    if len(set(cs)) > 1:
        graphs["chemsys"] = (*chemsys_graph(cs), 1)
    for g, (A, X, nf) in graphs.items():
        for seed in SEEDS:
            r, emb = run(A, X, seed=seed, normalize_feats=nf)
            r["normalize_feats"] = nf
            r.update(dataset=name, graph=g)
            if emb is not None and seed == SEEDS[0]:
                np.save(f"/tmp/claude-0/data/emb_{TAG}_{name}_{g}.npy", emb.numpy())
            out.append(r)
            print(json.dumps({k: v for k, v in r.items() if k != "val_curve"}), flush=True)
            json.dump(out, open(f"/tmp/claude-0/data/hgcn_sweep_{TAG}.json", "w"), indent=1)
print(f"TOTAL_WALL_SEC {time.time() - t_all:.1f}", flush=True)
