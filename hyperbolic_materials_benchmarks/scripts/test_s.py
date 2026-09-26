import sys, numpy as np, networkx as nx
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from hyp import s_score_exact, s_score_sampled
D = lambda G: np.asarray(nx.floyd_warshall_numpy(G), float)
for n in (2, 3, 5):   # Quraishi: s(L_n) = 2n/(2n+1) for (n+1)x(n+1) lattice
    print(f"L_{n}: s={s_score_exact(D(nx.grid_2d_graph(n+1, n+1))):.4f} expected {2*n/(2*n+1):.4f}")
print("tree s =", s_score_exact(D(nx.balanced_tree(2, 5))))
print("C12 s =", s_score_exact(D(nx.cycle_graph(12))), "sampled", s_score_sampled(D(nx.cycle_graph(12))))
