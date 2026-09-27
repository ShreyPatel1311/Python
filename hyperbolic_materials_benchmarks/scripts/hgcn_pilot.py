"""Timing pilot: HGCN repo (HazyResearch/hgcn) link prediction on our graphs, CPU.
Graphs: (1) MACE kNN10 graph (nodes = materials, features = MACE invariant descriptors);
        (2) chemical-system inclusion graph (nodes = chemical systems, features = element-membership vector).
Models: HGCN (Hyperboloid) vs GCN (Euclidean), repo defaults (epochs<=5000, patience 100, min-epochs 100)."""
import itertools, json, pickle, sys, time
import numpy as np, torch
sys.path.insert(0, "/tmp/claude-0/hgcn")
sys.path.insert(1, __file__.rsplit("/", 1)[0])
from config import parser
import optimizers
from models.base_models import LPModel
from utils.data_utils import mask_edges, process
from run_delta import knn_adj

torch.set_num_threads(4)
name = sys.argv[1] if len(sys.argv) > 1 else "Carbon-24"
max_epochs = int(sys.argv[2]) if len(sys.argv) > 2 else 5000


def chemsys_graph(chemsyss):
    nodes = set()
    for cs in chemsyss:
        els = tuple(sorted(cs.split("-")))
        for r in range(1, len(els) + 1):
            nodes.update(itertools.combinations(els, r))
    nodes = sorted(nodes); ix = {s: i for i, s in enumerate(nodes)}
    from pymatgen.core import Element
    X = np.zeros((len(nodes), 119))
    for s, i in ix.items():
        for el in s:
            X[i, Element(el).Z] = 1
    e = [(ix[s], ix[tuple(x for x in s if x != el)]) for s in nodes if len(s) > 1 for el in s]
    import scipy.sparse as sp
    n = len(nodes); e = np.array(e)
    A = sp.csr_matrix((np.ones(2 * len(e)), (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])), shape=(n, n))
    A.data[:] = 1
    return A, X


def run(A, X, model, manifold, seed):
    args = parser.parse_args([])
    args.task, args.model, args.manifold = "lp", model, manifold
    args.dataset, args.epochs, args.seed, args.split_seed = "custom", max_epochs, seed, seed
    # README link-prediction examples: HGCN (airport) dropout 0, wd 0, c None; GCN (cora) dropout 0.2, wd 0
    args.dim, args.num_layers, args.lr, args.weight_decay = 16, 2, 0.01, 0.0
    args.dropout = 0.0 if model == "HGCN" else 0.2
    args.act, args.bias, args.c = "relu", 1, None if model == "HGCN" else 1.0
    args.device = "cpu"; args.patience = 100; args.log_freq = 10 ** 9; args.eval_freq = 1
    np.random.seed(seed); torch.manual_seed(seed)
    data = {}
    (adj_train, tr, trf, va, vaf, te, tef) = mask_edges(A, args.val_prop, args.test_prop, seed)
    data.update(adj_train=adj_train, train_edges=tr, train_edges_false=trf, val_edges=va, val_edges_false=vaf,
                test_edges=te, test_edges_false=tef)
    data["adj_train_norm"], data["features"] = process(adj_train, X, args.normalize_adj, args.normalize_feats)
    args.n_nodes, args.feat_dim = data["features"].shape
    args.nb_false_edges, args.nb_edges = len(trf), len(tr)
    args.lr_reduce_freq = args.epochs
    m = LPModel(args)
    opt = getattr(optimizers, args.optimizer)(params=m.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    best_val, best_test, counter, t0 = m.init_metric_dict(), None, 0, time.time()
    for epoch in range(args.epochs):
        m.train(); opt.zero_grad()
        emb = m.encode(data["features"], data["adj_train_norm"])
        loss = m.compute_metrics(emb, data, "train")["loss"]; loss.backward(); opt.step()
        m.eval()
        with torch.no_grad():
            emb = m.encode(data["features"], data["adj_train_norm"])
            if not torch.isfinite(emb).all():
                return dict(model=model, seed=seed, epochs=epoch + 1, sec=time.time() - t0, diverged=True,
                            test_roc=float(best_test["roc"]) if best_test else None, n_nodes=int(A.shape[0]))
            val = m.compute_metrics(emb, data, "val")
        if m.has_improved(best_val, val):
            best_val, best_test, counter = val, m.compute_metrics(emb, data, "test"), 0
        else:
            counter += 1
            if counter == args.patience and epoch > args.min_epochs:
                break
    return dict(model=model, seed=seed, epochs=epoch + 1, sec=time.time() - t0,
                sec_per_epoch=(time.time() - t0) / (epoch + 1),
                test_roc=float(best_test["roc"]), test_ap=float(best_test["ap"]), n_nodes=int(A.shape[0]),
                n_edges=int(A.nnz // 2))


samples = pickle.load(open("/tmp/claude-0/data/samples.pkl", "rb"))
Xm = np.load(f"/tmp/claude-0/data/mace_{name}.npy")
graphs = {"mace_knn10": (knn_adj(Xm, 10), Xm)}
if len({r["chemsys"] for r in samples[name][:1000]}) > 1:
    graphs["chemsys"] = chemsys_graph([r["chemsys"] for r in samples[name][:1000]])
out = []
for gname, (A, X) in graphs.items():
    for model, manifold in (("HGCN", "PoincareBall"), ("GCN", "Euclidean")):
        r = run(A, X, model, manifold, seed=0); r["graph"] = gname; out.append(r)
        print(json.dumps(r), flush=True)
json.dump(out, open(f"/tmp/claude-0/data/hgcn_pilot_{name}.json", "w"), indent=1)
