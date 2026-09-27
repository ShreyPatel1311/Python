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

## Session 2 (2026-09-26): Vast.ai small-subset runs
Compute: Vast.ai (results returned through the container log, `scripts/vast_job.sh`); total spend $1.29. Raw outputs in
`results/vast_small/`. Subset sizes: 500 samples per dataset (δ, HGCN graphs), 600 structures / 40 epochs (force models),
1,500 JARVIS EFG structures; 3 seeds. These are small-run numbers, not converged benchmarks.

Fixes found while running: ASE zeroes FixAtoms forces unless `apply_constraint=False` (OC20); rMD17 file order is not time
order (pair by `old_indices`); MP 2025-09-25 build collections use numeric IDs, MPtrj alphabetical IDs — converted with
`emmet.core.mpid.AlphaID` (7310/7332 dielectric, 3313/3322 piezoelectric matched, chemsys agreement 1.0); per-element
reference energies of elements absent from a 480-structure training split are 0, so force-model test metrics use
seen-element structures (`test_seen`).

1. **Task c** (`results_main_new.json`, `results_mace_new.json`, `results_null_new.json`, `sensitivity_new.json`):
   molecular sets have the lowest per-structure δ_rel (MD22 0.22, rMD17 0.21); OC20 / OMat24 / JARVIS 8 Å clusters
   0.61–0.73. MACE-MP-0 embedding curvature estimate vs permutation null: rMD17 2.90×, MD22 2.52× (pooled 7–10 molecules;
   not tested whether molecule clusters cause this), JARVIS piezo / dielectric 1.39× / 1.37×, OC20 0.89×, OMat24 0.60–0.82×,
   JARVIS elastic 0.99×. No energy cliffs (<0.05 Å, >0.1 eV/atom) in MD22 / rMD17 pairs.
2. **HGCN divergence** (`hgcn_sweep_*`): in all 43 diverged runs a trainable curvature was ≤ 0 at the last finite step
   (gradient norm 0.015–0.46); gradient clipping alone: 93 % diverged; clipping + curvature bounds [0.01, 100]: 0 %.
3. **Learned curvature in models with a log₀ readout**: the last curvature cancels (exp and log at the same c), gets no
   gradient and stays at its initial value; the previous session's "HGCN learned curvature stayed 1.000" (energy
   regression) is this effect. Only inner-layer curvatures are informative.
4. **Distance-aware hyperbolic force model vs Euclidean twin vs MACE** (`hf_*`): Euclidean twin ≤ hyperbolic on force MAE
   on OC20, MP-ALOE, MD22; MACE best on MD22 (0.054 vs 0.204–0.219 eV/Å). Inner curvatures 0.75–1.07. Hyperbolic
   embeddings move 1.8–5× more per unit displacement (relative to their spread) without lower force error.
5. **Per-atom tensor targets** (`node_*`, `efgT_*`): JARVIS EFG tensors are in the Cartesian frame of the stored lattice
   for 89.7 % of orbits with site symmetry. HGCN on atom graphs (EFG eigenvalues, |F|): inner curvatures up to 1.39;
   equivariant full-tensor EFG model: curvatures 0.74–0.93, Euclidean twin slightly better (tensor MAE 12.27 vs 12.79).

Open: HGCN curvature on graph-level (per-structure) targets per dataset not yet measured.

### Session 2, later runs: HGCN curvature on tensor-derived / per-atom targets (no link prediction)
- **Graph-level, rotation-invariant tensor targets** (`graph_*`; 1,500 structures, 3 seeds, HGCN with per-layer trainable
  curvature, clip + bounds): MP dielectric eigenvalues, MP piezoelectric tensor norm, MP / JARVIS Voigt K and G, JARVIS
  OptB88vdW ε trace/3. Inner-layer curvature at the best epoch 0.94–1.26 (last epoch ≤ 1.36); HGCN ≈ GCN.
- **Per-atom targets** (`node_*`; 600 structures, 3 seeds): |F| on MPtrj, OC20, OMat24 (2 subsets), |magmom| on MPtrj,
  MatPES, MP-ALOE, Bader charge on MatPES. Inner-layer curvature at the best epoch 0.91–1.31 (last epoch ≤ 1.38). For
  |magmom| and Bader charge both HGCN and GCN are worse than the per-element mean baseline (not learned).
- **Link-prediction early-stopping rule** (HGCN repo `train.py`: `counter == patience and epoch > min_epochs`) never
  fires if the patience count is reached before `min_epochs`; the 5 runs that hit the 5,000-epoch cap are the single-seed
  high-curvature outliers (5.16–7.24) and their curvature was recorded ~4,700 epochs after the best validation epoch.
- **Curvature dynamics** (`results/vast_small/curvature_dynamics/`; HGCN, 3 seeds, patience 50, ≤ 300 epochs): with the
  curvature learning rate raised from 1e-3 to 0.05, learned curvature reaches 2.5–9.8 (MPtrj |F|) and 3.0–5.1
  (JARVIS elastic, layer 2); started at 5 it stays at 6–14 / 4–10. Test MAE is unchanged across settings (MPtrj |F|
  0.255 / 0.257 / 0.252 eV/Å; JARVIS elastic 24.07 / 23.91 / 24.69 GPa); the tree control reaches MAE 0.002 at every
  setting. MP dielectric eigenvalues (1,500 structures): layer-2 curvature at best epoch 1.16–1.24 (lr 1e-3), 2.6–6.6
  (lr 0.05), 7.5–11.2 (start 5); mean test MAE 33.03 / 32.12 / 29.70 vs mean-predictor baseline 32.09, i.e. HGCN does
  not beat the mean predictor on the largest eigenvalue (MAE 73.6–99.4 at lr 1e-3/0.05 start 1 vs baseline 73.5). Learned curvature here reflects optimizer settings, not the dataset, consistent with HGCN Theorem 4.1
  (Chami et al. 2019: the same performance is reachable at any curvature by rescaling embeddings).
