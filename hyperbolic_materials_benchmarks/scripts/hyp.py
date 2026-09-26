"""Gromov delta-hyperbolicity utilities.

Protocols implemented:
  * HGCN (Chami et al. 2019, arXiv:1910.12933; code: HazyResearch/hgcn utils/hyperbolicity.py):
    unweighted shortest-path (hop) distances, sample 50,000 random 4-tuples, delta = max over
    samples of (largest - second largest of the three pair sums) / 2.
  * Exact four-point delta over all 4-tuples (same quantity, no sampling) for small graphs.
  * Khrulkov et al. 2020 (arXiv:1904.02239): Gromov-product matrix w.r.t. a fixed base point,
    delta = max((A (x) A) - A) with the max-min product; delta_rel = 2*delta/diam.
"""
import numpy as np
import numba as nb
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import shortest_path, connected_components


def largest_cc(adj):
    """adj: scipy sparse symmetric adjacency. Returns (sub-adjacency, node indices, fraction)."""
    n_comp, lab = connected_components(adj, directed=False)
    if n_comp == 1:
        return adj, np.arange(adj.shape[0]), 1.0
    big = np.bincount(lab).argmax()
    idx = np.where(lab == big)[0]
    return adj[idx][:, idx], idx, len(idx) / adj.shape[0]


def hop_distances(adj):
    """All-pairs unweighted shortest-path lengths (BFS)."""
    return shortest_path(adj, method="D", unweighted=True, directed=False)


def edges_to_adj(n, edges):
    edges = np.asarray(edges, dtype=np.int64).reshape(-1, 2)
    edges = edges[edges[:, 0] != edges[:, 1]]
    data = np.ones(len(edges) * 2)
    r = np.concatenate([edges[:, 0], edges[:, 1]])
    c = np.concatenate([edges[:, 1], edges[:, 0]])
    a = csr_matrix((data, (r, c)), shape=(n, n))
    a.data[:] = 1.0
    return a


def delta_sampled(D, num_samples=50000, seed=0):
    """HGCN protocol on a precomputed distance matrix (finite entries only)."""
    n = D.shape[0]
    if n < 4:
        return 0.0
    rng = np.random.default_rng(seed)
    # 4 distinct nodes per sample (np.random.choice(..., replace=False) in HGCN)
    q = np.argsort(rng.random((num_samples, n)), axis=1)[:, :4] if n <= 64 else _distinct4(rng, n, num_samples)
    a, b, c, d = q.T
    s = np.stack([D[a, b] + D[c, d], D[a, c] + D[b, d], D[a, d] + D[b, c]], axis=1)
    s.sort(axis=1)
    return float(((s[:, 2] - s[:, 1]) / 2).max())


def _distinct4(rng, n, m):
    q = rng.integers(0, n, size=(m, 4))
    bad = np.ones(m, bool)
    while bad.any():
        qs = np.sort(q, axis=1)
        bad = (np.diff(qs, axis=1) == 0).any(axis=1)
        q[bad] = rng.integers(0, n, size=(bad.sum(), 4))
    return q


@nb.njit(parallel=True, cache=True)
def delta_exact(D):
    """Exact four-point delta, O(n^4/24)."""
    n = D.shape[0]
    best = np.zeros(n)
    for i in nb.prange(n):
        m = 0.0
        for j in range(i + 1, n):
            dij = D[i, j]
            for k in range(j + 1, n):
                dik = D[i, k]
                djk = D[j, k]
                for l in range(k + 1, n):
                    s1 = dij + D[k, l]
                    s2 = dik + D[j, l]
                    s3 = D[i, l] + djk
                    # (largest - second largest)/2
                    if s1 >= s2:
                        hi, lo = s1, s2
                    else:
                        hi, lo = s2, s1
                    if s3 >= hi:
                        v = s3 - hi
                    elif s3 >= lo:
                        v = hi - s3
                    else:
                        v = hi - lo
                    if v > m:
                        m = v
        best[i] = m
    return best.max() / 2.0


@nb.njit(parallel=True, cache=True)
def _maxmin_minus(A):
    n = A.shape[0]
    out = np.zeros(n)
    for i in nb.prange(n):
        m = 0.0
        for j in range(n):
            mm = -1e300
            for k in range(n):
                v = A[i, k] if A[i, k] < A[k, j] else A[k, j]
                if v > mm:
                    mm = v
            if mm - A[i, j] > m:
                m = mm - A[i, j]
        out[i] = m
    return out.max()


def delta_fixed_base(D, w=0):
    """Khrulkov et al. 2020 Eq. (2)+(4): Gromov products w.r.t. base point w, max-min product."""
    A = 0.5 * (D[w][:, None] + D[w][None, :] - D)
    return float(_maxmin_minus(np.ascontiguousarray(A)))


def summarize(D, num_samples=50000, seed=0, exact_max_n=400):
    D = np.asarray(D, dtype=np.float64)
    n = D.shape[0]
    diam = float(D.max()) if n else 0.0
    out = {"n": n, "diam": diam}
    out["delta_hgcn"] = delta_sampled(D, num_samples, seed)
    out["delta_exact"] = float(delta_exact(D)) if n <= exact_max_n else np.nan
    out["delta_rel_hgcn"] = 2 * out["delta_hgcn"] / diam if diam > 0 else 0.0
    out["delta_rel_exact"] = 2 * out["delta_exact"] / diam if diam > 0 and n <= exact_max_n else np.nan
    return out


@nb.njit(parallel=True, cache=True)
def _gamma_exact(D, dmax):
    """Gamma_G(x) = max delta over quadruples with quadruple-diameter x (Quraishi 2026, arXiv:2607.24096).
    Integer (hop) distances assumed. Returns 2*Gamma per diameter (integer arithmetic)."""
    n = D.shape[0]
    G = np.zeros((n, dmax + 1), dtype=np.int64)
    for i in nb.prange(n):
        for j in range(i + 1, n):
            dij = int(D[i, j])
            for k in range(j + 1, n):
                dik = int(D[i, k]); djk = int(D[j, k])
                for l in range(k + 1, n):
                    dil = int(D[i, l]); djl = int(D[j, l]); dkl = int(D[k, l])
                    s1 = dij + dkl; s2 = dik + djl; s3 = dil + djk
                    hi = max(s1, max(s2, s3)); lo = min(s1, min(s2, s3))
                    mid = s1 + s2 + s3 - hi - lo
                    diam = max(max(max(dij, dik), max(djk, dil)), max(djl, dkl))
                    if hi - mid > G[i, diam]:
                        G[i, diam] = hi - mid
    out = np.zeros(dmax + 1, dtype=np.int64)
    for i in range(n):
        for x in range(dmax + 1):
            if G[i, x] > out[x]:
                out[x] = G[i, x]
    return out


def s_score_from_gamma(two_gamma, D):
    """s(G) = 4 * sum_{i in Dist_G} Gamma(i) / (D(G)(D(G)+1)) (Quraishi 2026, Def. 4.2)."""
    Dg = int(two_gamma.shape[0] - 1)
    if Dg <= 0:
        return 0.0
    return float(4 * (two_gamma.sum() / 2.0) / (Dg * (Dg + 1)))


def s_score_exact(D):
    dmax = int(D.max())
    return s_score_from_gamma(_gamma_exact(np.ascontiguousarray(D), dmax), D)


def s_score_sampled(D, num_samples=50000, seed=0):
    """Sampled lower-bound estimate of s(G) using the same random 4-tuples as the HGCN protocol."""
    n = D.shape[0]
    dmax = int(D.max())
    if n < 4 or dmax == 0:
        return 0.0
    rng = np.random.default_rng(seed)
    q = _distinct4(rng, n, num_samples)
    a, b, c, d = q.T
    s = np.stack([D[a, b] + D[c, d], D[a, c] + D[b, d], D[a, d] + D[b, c]], axis=1)
    s.sort(axis=1)
    two_delta = (s[:, 2] - s[:, 1]).astype(np.int64)
    diam = np.max(np.stack([D[a, b], D[a, c], D[a, d], D[b, c], D[b, d], D[c, d]], 1), 1).astype(np.int64)
    g = np.zeros(dmax + 1, dtype=np.int64)
    np.maximum.at(g, diam, two_delta)
    return s_score_from_gamma(g, D)
