"""Validation of hyp.py against known cases and a brute-force reference."""
import itertools, sys, time
import numpy as np
import networkx as nx
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from hyp import delta_exact, delta_sampled, delta_fixed_base, hop_distances

def D_of(G):
    return np.asarray(nx.floyd_warshall_numpy(G), dtype=np.float64)

def brute(D):
    n = len(D); m = 0
    for a, b, c, d in itertools.combinations(range(n), 4):
        s = sorted([D[a, b] + D[c, d], D[a, c] + D[b, d], D[a, d] + D[b, c]])
        m = max(m, (s[2] - s[1]) / 2)
    return m

rng = np.random.default_rng(0)
# 1) brute-force agreement on random graphs
for t in range(5):
    G = nx.connected_watts_strogatz_graph(20, 4, 0.3, seed=t)
    D = D_of(G)
    assert abs(delta_exact(D) - brute(D)) < 1e-12, "exact != brute"
print("exact == brute force on 5 random graphs: OK")
# 2) trees -> 0 (HGCN: delta = 0 for trees)
T = nx.balanced_tree(3, 4); D = D_of(T)
print("balanced tree(3,4): exact", delta_exact(D), "sampled", delta_sampled(D), "fixed-base", delta_fixed_base(D))
T = nx.random_labeled_tree(200, seed=1); D = D_of(T)
print("random tree n=200: exact", delta_exact(D))
# 3) cycles, grids (non-hyperbolic references)
for n in (8, 12, 16):
    D = D_of(nx.cycle_graph(n)); print(f"cycle C{n}: exact {delta_exact(D)} diam {D.max()}")
for L in (4, 6, 8):
    D = D_of(nx.grid_2d_graph(L, L)); print(f"2D grid {L}x{L}: exact {delta_exact(D)} diam {D.max()} rel {2*delta_exact(D)/D.max():.3f}")
for L in (3, 5):
    D = D_of(nx.grid_graph([L, L, L])); print(f"3D grid {L}^3: exact {delta_exact(D)} diam {D.max()} rel {2*delta_exact(D)/D.max():.3f}")
# 4) sampled <= exact; fixed-base in [exact/2, exact]
G = nx.connected_watts_strogatz_graph(300, 6, 0.1, seed=3); D = D_of(G)
t = time.time(); e = delta_exact(D); te = time.time() - t
s = delta_sampled(D); f = max(delta_fixed_base(D, w) for w in range(5))
print(f"WS n=300: exact {e} ({te:.1f}s) sampled {s} fixedbase {f}")
assert s <= e + 1e-12 and f <= e + 1e-12 and e <= 2 * f + 1e-12
print("bounds OK")
