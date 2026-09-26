# Gromov δ-hyperbolicity of materials-science benchmarks

All numbers below were computed on CPU in one cloud session (2026-09-26); no Vast.ai compute was used
(the environment's network policy denied `console.vast.ai`). Raw outputs are in `results/`, code in `scripts/`.

## Method
- **δ (HGCN protocol)** — Chami et al. 2019, [arXiv:1910.12933](https://arxiv.org/abs/1910.12933); code
  `HazyResearch/hgcn/utils/hyperbolicity.py`: unweighted hop distances, 50,000 random 4-tuples,
  δ = max (largest − second-largest pair sum)/2. Exact enumeration used for graphs ≤ 260 nodes.
- **δ_rel = 2δ/diam** and fixed-base-point max–min algorithm — Khrulkov et al. 2020,
  [arXiv:1904.02239](https://arxiv.org/abs/1904.02239).
- **s(G)** diameter-normalised hyperbolicity — Quraishi 2026, [arXiv:2607.24096](https://arxiv.org/abs/2607.24096) (preprint).
- **Curvature estimate** c(X) = (0.144/δ_rel)² — Khrulkov et al. 2020, Eq. 5.
- Validation (`scripts/test_hyp.py`, `scripts/test_s.py`): exact δ = brute force; trees 0; cycle Cₙ n/4;
  2D grid δ_rel 1.0; 3D grid 0.667; s(Lₙ) = 2n/(2n+1).

## Datasets sampled (host reachable in the session)
MPtrj, MatPES 2025.1, MP-ALOE (Materials Project `materialsproject-contribs` S3); MP elasticity / dielectric /
piezoelectric (`materialsproject-build` S3); MP molecules (MPcules); GNoME (GCS); QM9 (DeepChem S3);
MP-20 / Perov-5 / Carbon-24 (CDVAE GitHub). 2,000 records per dataset, fixed seeds.
Not measured (hosts blocked): OC20, OMat24, rMD17, MD22, Matbench, Matbench Discovery, JARVIS.

## Key results
1. **Per-structure graphs** (`results/results_main.json`): lowest δ for molecular bond graphs
   (QM9 / MPcules mean δ 0.70 / 0.73, δ_rel 0.23, s 0.31). Crystal clusters (8 Å) are lattice-like
   (δ_rel 0.62–0.79, s 0.64–0.82).
2. **Dataset-level MACE-MP-0 embeddings vs per-feature permutation null** (`results_mace.json`, `results_null.json`):
   only Carbon-24 separates on the kNN graph (δ_rel 0.25 vs 1.00; s 0.30 vs 0.60).
3. **Curvature estimate from Euclidean δ_rel of MACE embeddings**: MP-ALOE c = 1.50 vs null 0.53 (2.8×),
   MatPES 1.35×, Carbon-24 1.33×, MP-20 1.31×, MP-elasticity 1.29×; H² disk reference c = 1.55.
4. **Hierarchies**: chemical-system inclusion graph s = 0.33–0.44; symmetry tree δ = 0 by construction;
   space-group maximal-subgroup graph δ = 2.5, s = 0.81.
5. **HGCN link prediction** (constructed graphs; not a dataset target) — `hgcn_sweep_HGCN_sweep_seed0.json`:
   23 runs, 14 diverged. Matched HGCN vs GCN on MPtrj: MACE-kNN graph 0.981 vs 0.953 ROC,
   chemical-system graph 0.982 vs 0.894 (1 seed).
6. **HGCN vs GCN, MPtrj energy/atom regression** (3,000 structures, 3 seeds; `energy_*.json`):
   HGCN 0.365 ± 0.009, GCN 0.317 ± 0.001, per-element linear 0.540, mean 1.439 eV/atom;
   MACE-MP-0 zero-shot 0.013 eV/atom (trained on MPtrj — leakage). HGCN learned curvature stayed 1.000.
7. **Displacement sensitivity** (`sensitivity.json`, consecutive trajectory frames): MPtrj energy cliffs
   (<0.05 Å, >0.1 eV/atom) 4 / 11,557; MP-ALOE 0 / 1,598. Median |F|: MPtrj 0.10, MP-ALOE 0.11,
   MatPES 0.60 eV/Å. Band-gap / magmom sensitivity not measurable (missing on intermediate frames).

## Reproducing
Scripts use absolute paths under `/tmp/claude-0/` (venv `/tmp/claude-0/venv`, data `/tmp/claude-0/data`,
HGCN clone `/tmp/claude-0/hgcn`). Order: `load_samples.py` → `fix_tensor_samples.py` → `run_delta.py`
→ `embed_mace.py` → `null_models.py`; HGCN: clone `HazyResearch/hgcn`, apply `hgcn_torch2_compat.patch`
(out-of-place `renorm`, numerically identical), then `hgcn_sweep.py` / `hgcn_energy.py`; `sensitivity.py`.
Run from a directory other than the repo root (the repo's `queue.py` shadows Python's `queue` module).

## Open issues
- HGCN divergence in 14/23 link-prediction runs (double precision + feature standardisation did not remove it).
- GCN link-prediction baseline run only on MPtrj.
- Learned-curvature measurement per dataset not yet done.
