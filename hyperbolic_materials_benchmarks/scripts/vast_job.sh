#!/usr/bin/env bash
# Vast.ai job (image pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime), one instance per JOB:
#   JOB=c         task c: new-dataset samples, delta, sensitivity, MACE-MP-0 embeddings + permutation nulls
#   JOB=d         task d: rebuild old samples, MACE-MP-0 embeddings, HGCN link prediction without / with divergence
#                 fixes and GCN baselines (3 seeds), one process per (config, dataset)
#   JOB=be:<DS>   tasks b+e on DS in {MP-ALOE, MatPES, MD22, OC20}: hyp_force.py HYP / EUC + mace_baseline.py, 3 seeds
#   JOB=cdyn      curvature-dynamics test on one dataset (CDYN = MPtrj:F | TREE | MP-dielectric | JARVIS-elastic):
#                 HGCN x 3 seeds x {C_LR 1e-3 init 1, C_LR 0.05 init 1, C_LR 0.05 init 5}, patience 50, <= 300 epochs
#   JOB=atom      per-atom HGCN / GCN regression: |F| (MPtrj, OC20, OMat24 x2), |magmom| (MPtrj, MatPES, MP-ALOE),
#                 Bader charge (MatPES); 600 structures, 3 seeds; ATOM_DS selects a subset (one instance per dataset)
#   JOB=tgraph    graph-level HGCN / GCN regression of rotation-invariant tensor targets (tensor_targets.py:
#                 MP dielectric / piezoelectric / elasticity, JARVIS elastic / OptB88vdW dielectric), 3 seeds
#   JOB=tensor    per-atom tensor targets: (1) hgcn_node.py HGCN / GCN on atom graphs, rotation-invariant targets
#                 (JARVIS EFG eigenvalues, MP-ALOE / MatPES |F|); (2) hyp_efg.py HYP / EUC full EFG tensors; 3 seeds
#   JOB=sweep     one setting of an HGCN sweep on one dataset (SW_DS; graph-level: MP-dielectric | MP-piezoelectric |
#                 MP-elasticity | JARVIS-elastic | JARVIS-eps-optB88, 1500 structures, <= 150 epochs; per-atom: EFG | MP-ALOE |
#                 MatPES | <SRC>:F|mag|bader as in JOB=atom / tensor, <= 60 epochs), 3 seeds, default patience 20:
#                 SW_KIND=dim  -> embedding size DIM=SW_VAL, HGCN (trainable curvature) and GCN
#                 SW_KIND=curv -> HGCN with every curvature fixed to C_FIX=SW_VAL (embedding size 64)
#   JOB=hgcn      HGCN link prediction (FIX=clip+cbound, 3 seeds) on the materials datasets not in task d: MP dielectric /
#                 piezoelectric, OC20, OMat24 (2 subsets), JARVIS (3 tensor subsets)
# SSH is unavailable from the controlling session, so results leave the instance only through the container log:
# after the work (or at WALL seconds) a gzip+base64 archive of the result JSONs and logs is printed between
# RESULTS_B64_BEGIN / RESULTS_B64_END in 300-character lines (the log service truncates lines at ~500 characters);
# the last 15 lines of each failed job log are also printed. Then the container idles until destroyed.
# Env: JOB, BRANCH, POOL (c/d samples per dataset, 500), N_EMB (500), NSTRUCT (600), MAX_EP (40), SEEDS3 ("0 1 2"),
#      PAR (parallel processes, 16 for d / 9 for be), WALL (5400), SWEEP_ONLY (d: space-separated dataset names)
set -uo pipefail
JOB=${JOB:?set JOB}; BRANCH=${BRANCH:-claude/material-science-hyperbolic-benchmarks-cfvr0n}
POOL=${POOL:-500}; N_EMB=${N_EMB:-500}; NSTRUCT=${NSTRUCT:-600}; MAX_EP=${MAX_EP:-40}; SEEDS3=${SEEDS3:-"0 1 2"}
WALL=${WALL:-5400}
D=/tmp/claude-0/data; L=/tmp/claude-0/logs; mkdir -p $D $L
T0=$(date +%s); say() { echo "[$(( $(date +%s) - T0 ))s] $JOB $*"; }
say "start $(nvidia-smi -L | head -1) cores=$(nproc)"
apt-get -qq update >/dev/null 2>&1; apt-get -qq install -y git curl unzip xz-utils >/dev/null 2>&1
git clone -q --depth 1 -b "$BRANCH" https://github.com/ShreyPatel1311/Python /root/repo || { say "clone failed"; sleep 36000; }
S=/root/repo/hyperbolic_materials_benchmarks/scripts
PKG="numpy scipy numba pandas pyarrow scikit-learn networkx ase mace-torch"
case $JOB in
  c) PKG="$PKG pymatgen ase-db-backends" ;;
  d) PKG="$PKG pymatgen rdkit fsspec aiohttp emmet-core"
     git clone -q https://github.com/HazyResearch/hgcn /tmp/claude-0/hgcn && (cd /tmp/claude-0/hgcn &&
       git checkout -q a526385744da25fc880f3da346e17d0fe33817f8 && git apply /root/repo/hyperbolic_materials_benchmarks/hgcn_torch2_compat.patch) ;;
  sweep) PKG="$PKG pymatgen emmet-core ase-db-backends"
     git clone -q https://github.com/HazyResearch/hgcn /tmp/claude-0/hgcn && (cd /tmp/claude-0/hgcn &&
       git checkout -q a526385744da25fc880f3da346e17d0fe33817f8 && git apply /root/repo/hyperbolic_materials_benchmarks/hgcn_torch2_compat.patch) ;;
  cdyn) PKG="$PKG pymatgen emmet-core"
     git clone -q https://github.com/HazyResearch/hgcn /tmp/claude-0/hgcn && (cd /tmp/claude-0/hgcn &&
       git checkout -q a526385744da25fc880f3da346e17d0fe33817f8 && git apply /root/repo/hyperbolic_materials_benchmarks/hgcn_torch2_compat.patch) ;;
  atom) PKG="$PKG ase-db-backends"
     git clone -q https://github.com/HazyResearch/hgcn /tmp/claude-0/hgcn && (cd /tmp/claude-0/hgcn &&
       git checkout -q a526385744da25fc880f3da346e17d0fe33817f8 && git apply /root/repo/hyperbolic_materials_benchmarks/hgcn_torch2_compat.patch) ;;
  tgraph) PKG="$PKG pymatgen emmet-core"
     git clone -q https://github.com/HazyResearch/hgcn /tmp/claude-0/hgcn && (cd /tmp/claude-0/hgcn &&
       git checkout -q a526385744da25fc880f3da346e17d0fe33817f8 && git apply /root/repo/hyperbolic_materials_benchmarks/hgcn_torch2_compat.patch) ;;
  tensor) PKG="$PKG pymatgen"
     git clone -q https://github.com/HazyResearch/hgcn /tmp/claude-0/hgcn && (cd /tmp/claude-0/hgcn &&
       git checkout -q a526385744da25fc880f3da346e17d0fe33817f8 && git apply /root/repo/hyperbolic_materials_benchmarks/hgcn_torch2_compat.patch) ;;
  hgcn) PKG="$PKG pymatgen ase-db-backends emmet-core"
     git clone -q https://github.com/HazyResearch/hgcn /tmp/claude-0/hgcn && (cd /tmp/claude-0/hgcn &&
       git checkout -q a526385744da25fc880f3da346e17d0fe33817f8 && git apply /root/repo/hyperbolic_materials_benchmarks/hgcn_torch2_compat.patch) ;;
  be:*) git clone -q https://github.com/HazyResearch/hgcn /tmp/claude-0/hgcn && (cd /tmp/claude-0/hgcn &&
       git checkout -q a526385744da25fc880f3da346e17d0fe33817f8 && git apply /root/repo/hyperbolic_materials_benchmarks/hgcn_torch2_compat.patch) ;;
esac
pip install -q $PKG > $L/pip.log 2>&1; say "pip exit $? torch=$(python -c 'import torch;print(torch.__version__, torch.cuda.is_available())')"
cd /tmp   # the repo root contains queue.py, which shadows the stdlib module
case $JOB in
  c) ITEMS="new" ;; d) ITEMS="old" ;; hgcn) ITEMS="mptrj mpcoll oc20 omat jarvis" ;; tensor) ITEMS="jarvis mpaloe matpes" ;; tgraph) ITEMS="mptrj jarvis" ;;
  sweep) case $SW_DS in MP-ALOE*) ITEMS="mpaloe" ;; MP-*|JARVIS-*) ITEMS="mptrj jarvis" ;; EFG) ITEMS="jarvis" ;; MPtrj:*) ITEMS="mptrj" ;;
         MatPES*) ITEMS="matpes" ;; OC20:*) ITEMS="oc20" ;; OMat24*) ITEMS="omat" ;; esac ;;
  cdyn) case $CDYN in TREE) ITEMS="none" ;; MPtrj:F) ITEMS="mptrj" ;; *) ITEMS="mptrj jarvis" ;; esac ;;
  atom) ITEMS=$(for d in ${ATOM_DS:-MPtrj:F MPtrj:mag MatPES:mag MatPES:bader MP-ALOE:mag OC20:F OMat24r:F OMat24a:F}; do
          case $d in MPtrj:*) echo mptrj ;; MatPES:*) echo matpes ;; MP-ALOE:*) echo mpaloe ;; OC20:*) echo oc20 ;; OMat24*) echo omat ;; esac
        done | sort -u | tr "\n" " ") ;;
  be:MP-ALOE) ITEMS="mpaloe" ;; be:MatPES) ITEMS="matpes" ;; be:MD22) ITEMS="md22ac" ;; be:OC20) ITEMS="oc20" ;;
esac
bash $S/download_data.sh $ITEMS > $L/download.log 2>&1; say "download exit $? $(du -sh $D | cut -f1)"
export OMP_NUM_THREADS=4 NUMBA_NUM_THREADS=16

emit() {
  python - "$1" <<'EOF'
import base64, glob, io, os, sys, tarfile
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tf:
    for f in sorted(glob.glob("/tmp/claude-0/data/*.json") + glob.glob("/tmp/claude-0/logs/*.log")
                    + glob.glob("/tmp/claude-0/data/mace_*_s*/*.log")):
        if f.endswith(("pip.log", "download.log")) or os.path.getsize(f) > 20_000_000:
            continue
        tf.add(f, arcname=f.split("/claude-0/")[1])
b = base64.b64encode(buf.getvalue()).decode()
print("RESULTS_B64_BEGIN", len(b), sys.argv[1], flush=True)
for i in range(0, len(b), 300):   # the Vast log service truncates lines at ~500 characters
    print("B64", i // 300, b[i:i + 300], flush=True)
print("RESULTS_B64_END", sys.argv[1], flush=True)
EOF
}

work_c() {
  python $S/load_samples_new.py $POOL > $L/samples_new.log 2>&1; say "samples_new exit $?"
  ( SAMPLES=$D/samples_new.pkl TAG=_new python $S/run_delta.py > $L/delta_new.log 2>&1; say "delta_new exit $?" ) &
  python $S/sensitivity_new.py > $L/sens_new.log 2>&1; say "sensitivity_new exit $?"
  DEVICE=cuda N_EMB=$N_EMB SAMPLES=$D/samples_new.pkl TAG=_new SKIP_REFS=1 python -W ignore $S/embed_mace.py > $L/mace_new.log 2>&1
  say "embed_new exit $?"
  SAMPLES=$D/samples_new.pkl TAG=_new python $S/null_models.py > $L/null_new.log 2>&1; say "null_new exit $?"
  wait
}

work_d() {
  POOL=$POOL python $S/load_samples.py > $L/samples_old.log 2>&1; say "samples_old exit $?"
  POOL=$POOL python $S/fix_tensor_samples.py >> $L/samples_old.log 2>&1; say "fix_tensor exit $?"
  DEVICE=cuda N_EMB=$N_EMB TAG=_rebuild SKIP_REFS=1 python -W ignore $S/embed_mace.py > $L/mace_old.log 2>&1; say "embed_old exit $?"
  python -c "import pickle; print('\n'.join(k for k, v in pickle.load(open('$D/samples.pkl', 'rb')).items() if v))" > $L/datasets.txt
  [ -n "${SWEEP_ONLY:-}" ] && printf '%s\n' $SWEEP_ONLY > $L/datasets.txt   # restrict sweeps to these datasets
  for cfg in "HGCN none" "HGCN clip" "HGCN clip+cbound" "GCN none"; do
    while read ds; do echo "$cfg $ds"; done < $L/datasets.txt
  done > $L/sweep_jobs.txt
  xargs -P ${PAR:-16} -L 1 bash -c 'FIX=$1 SEEDS=0,1,2 python -W ignore '$S'/hgcn_sweep.py $0 1 "$2" "$0_$1_$2" \
      > '$L'/sweep_$0_$1_$2.log 2>&1; e=$?; echo "[d] sweep $0 $1 $2 exit $e"; [ $e -ne 0 ] && tail -15 '$L'/sweep_$0_$1_$2.log | cut -c1-300 | sed "s/^/  | /"; true' < $L/sweep_jobs.txt
}

work_hgcn() {
  # tensor sets need only MPtrj + the MP collections (fix_tensor_samples.py starts from an empty samples.pkl)
  POOL=$POOL python $S/fix_tensor_samples.py > $L/samples_tensor.log 2>&1; say "tensor samples exit $?"
  python $S/load_samples_new.py $POOL > $L/samples_new.log 2>&1; say "samples_new exit $?"
  DEVICE=cuda N_EMB=$N_EMB TAG=_tensor SKIP_REFS=1 python -W ignore $S/embed_mace.py > $L/mace_tensor.log 2>&1; say "embed_tensor exit $?"
  DEVICE=cuda N_EMB=$N_EMB SAMPLES=$D/samples_new.pkl TAG=_new SKIP_REFS=1 python -W ignore $S/embed_mace.py > $L/mace_new.log 2>&1
  say "embed_new exit $?"
  { for ds in MP-dielectric MP-piezoelectric; do echo "$D/samples.pkl $ds"; done
    for ds in OC20-S2EF OMat24-rattled-300-subsampled OMat24-aimd-from-PBE-3000-nvt JARVIS-elastic JARVIS-piezo JARVIS-dielectric; do
      echo "$D/samples_new.pkl $ds"; done; } > $L/hgcn_jobs.txt
  xargs -P ${PAR:-16} -L 1 bash -c 'SAMPLES=$0 FIX=clip+cbound SEEDS=0,1,2 python -W ignore '$S'/hgcn_sweep.py HGCN 1 "$1" "HGCN_clip+cbound_$1" \
      > '$L'/sweep_HGCN_$1.log 2>&1; e=$?; echo "[hgcn] sweep $1 exit $e"; [ $e -ne 0 ] && tail -15 '$L'/sweep_HGCN_$1.log | cut -c1-300 | sed "s/^/  | /"; true' < $L/hgcn_jobs.txt
}

work_cdyn() {
  case $CDYN in MPtrj:F|TREE) SCRIPT=hgcn_node.py ;; *) SCRIPT=hgcn_graph.py
    python -W ignore $S/tensor_targets.py 1500 > $L/tensor_targets.log 2>&1; say "tensor_targets exit $?" ;; esac
  OUT=/tmp python -W ignore $S/$SCRIPT $CDYN HGCN 0 0 > $L/cache.log 2>&1; say "cache exit $?"
  for s in $SEEDS3; do for cfg in "0 1" "0.05 1" "0.05 5"; do set -- $cfg
    echo "$1 $2 $s"; done; done > $L/cdyn_jobs.txt
  xargs -P ${PAR:-9} -L 1 bash -c 'f='$L'/job_clr$0_init$1_s$2.log; C_LR=$0 C_INIT=$1 PATIENCE=50 RUN_TAG=_clr$0_init$1 OUT='$D' \
      python -W ignore '$S'/'$SCRIPT' '$CDYN' HGCN $2 300 > $f 2>&1; e=$?; echo "[cdyn] clr=$0 init=$1 seed=$2 exit $e"; [ $e -ne 0 ] && tail -15 $f | cut -c1-300 | sed "s/^/  | /"; true' < $L/cdyn_jobs.txt
}

work_sweep() {
  case $SW_DS in
    MP-dielectric|MP-piezoelectric|MP-elasticity|JARVIS-elastic|JARVIS-eps-optB88) SCRIPT=hgcn_graph.py; EP=${MAX_EP_G:-150}
      python -W ignore $S/tensor_targets.py ${N_TT:-1500} > $L/tensor_targets.log 2>&1; say "tensor_targets exit $?" ;;
    EFG) SCRIPT=hgcn_node.py; EP=${MAX_EP_T:-60}
      python -W ignore $S/efg_data.py ${N_EFG:-1500} > $L/efg_data.log 2>&1; say "efg_data exit $?" ;;
    *) SCRIPT=hgcn_node.py; EP=${MAX_EP_A:-60} ;;
  esac
  OUT=/tmp NT=${NT:-2} python -W ignore $S/$SCRIPT $SW_DS GCN 0 0 > $L/cache.log 2>&1; say "cache exit $?"
  case $SW_KIND in dim) MODELS="HGCN GCN"; ENV="DIM=$SW_VAL"; TAGV=_dim$SW_VAL ;; curv) MODELS=HGCN; ENV="C_FIX=$SW_VAL"; TAGV=_cfix$SW_VAL ;; esac
  for s in $SEEDS3; do for m in $MODELS; do echo "$m $s"; done; done > $L/sweep_jobs.txt
  xargs -P ${PAR:-6} -L 1 bash -c 'f='$L'/job_$0_s$1'$TAGV'.log; env '$ENV' RUN_TAG='$TAGV' NT=${NT:-2} OUT='$D' \
      python -W ignore '$S'/'$SCRIPT' '$SW_DS' $0 $1 '$EP' > $f 2>&1; e=$?; echo "[sweep] '$SW_DS' '$SW_KIND'='$SW_VAL' $0 seed=$1 exit $e"; [ $e -ne 0 ] && tail -15 $f | cut -c1-300 | sed "s/^/  | /"; true' < $L/sweep_jobs.txt
}

work_atom() {
  ATOM_DS=${ATOM_DS:-MPtrj:F MPtrj:mag MatPES:mag MatPES:bader MP-ALOE:mag OC20:F OMat24r:F OMat24a:F}
  for s in $SEEDS3; do for ds in $ATOM_DS; do
    for m in HGCN GCN; do echo "hgcn_node.py $ds $m $s ${MAX_EP_A:-60}"; done; done; done > $L/atom_jobs.txt
  # build each dataset cache once (seed-0 GCN, 0 epochs) before the parallel runs read it
  for ds in $ATOM_DS; do
    OUT=/tmp python -W ignore $S/hgcn_node.py $ds GCN 0 0 > $L/cache_$ds.log 2>&1; say "cache $ds exit $?"; done
  xargs -P ${PAR:-16} -I{} bash -c 'set -- {}; f='$L'/job_$(echo "$*" | tr " /:" "___").log; OUT='$D' python -W ignore '$S'/$* > $f 2>&1; e=$?; echo "[atom] $* exit $e"; [ $e -ne 0 ] && tail -15 $f | cut -c1-300 | sed "s/^/  | /"; true' < $L/atom_jobs.txt
}

work_tgraph() {
  python -W ignore $S/tensor_targets.py ${N_TT:-1500} > $L/tensor_targets.log 2>&1; say "tensor_targets exit $?"
  for s in $SEEDS3; do for ds in MP-dielectric MP-piezoelectric MP-elasticity JARVIS-elastic JARVIS-eps-optB88; do
    for m in HGCN GCN; do echo "hgcn_graph.py $ds $m $s ${MAX_EP_G:-150}"; done; done; done > $L/tgraph_jobs.txt
  xargs -P ${PAR:-16} -I{} bash -c 'set -- {}; f='$L'/job_$(echo "$*" | tr " /" "__").log; OUT='$D' python -W ignore '$S'/$* > $f 2>&1; e=$?; echo "[tgraph] $* exit $e"; [ $e -ne 0 ] && tail -15 $f | cut -c1-300 | sed "s/^/  | /"; true' < $L/tgraph_jobs.txt
}

work_tensor() {
  python -W ignore $S/efg_data.py ${N_EFG:-1500} > $L/efg_data.log 2>&1; say "efg_data exit $?"
  { for s in $SEEDS3; do for ds in EFG MP-ALOE MatPES; do for m in HGCN GCN; do echo "hgcn_node.py $ds $m $s ${MAX_EP_T:-60}"; done; done
      for m in HYP EUC; do echo "hyp_efg.py $m $s ${MAX_EP_T:-60} ${N_EFG:-1500}"; done; done; } > $L/tensor_jobs.txt
  xargs -P ${PAR:-12} -I{} bash -c 'set -- {}; f='$L'/job_$(echo "$*" | tr " /" "__").log; DEVICE=cuda OUT='$D' python -W ignore '$S'/$* > $f 2>&1; e=$?; echo "[tensor] $* exit $e"; [ $e -ne 0 ] && tail -15 $f | cut -c1-300 | sed "s/^/  | /"; true' < $L/tensor_jobs.txt
}

work_be() {
  ds=$1
  DEVICE=cuda OUT=$D python -W ignore $S/hyp_force.py $ds EUC 0 0 $NSTRUCT > $L/cache_$ds.log 2>&1
  DEVICE=cuda OUT=$D EXPORT_XYZ=1 python -W ignore $S/hyp_force.py $ds EUC 0 0 $NSTRUCT >> $L/cache_$ds.log 2>&1
  say "cache exit $?"; rm -f $D/hf_*_EUC_s0_n*.json
  for s in $SEEDS3; do
    for m in HYP EUC; do echo "hyp_force.py $ds $m $s $MAX_EP $NSTRUCT"; done
    echo "mace_baseline.py $ds $s $MAX_EP $NSTRUCT"
  done > $L/gpu_jobs.txt
  xargs -P ${PAR:-9} -I{} bash -c 'set -- {}; f='$L'/job_$(echo "$*" | tr " /" "__").log; DEVICE=cuda OUT='$D' python -W ignore '$S'/$* > $f 2>&1; e=$?; echo "[be] $* exit $e"; [ $e -ne 0 ] && tail -15 $f | cut -c1-300 | sed "s/^/  | /"; true' < $L/gpu_jobs.txt
}

case $JOB in c) work_c & ;; d) work_d & ;; hgcn) work_hgcn & ;; tensor) work_tensor & ;; tgraph) work_tgraph & ;; atom) work_atom & ;; cdyn) work_cdyn & ;; sweep) work_sweep & ;; be:*) work_be ${JOB#be:} & ;; esac
WP=$!
while kill -0 $WP 2>/dev/null && [ $(( $(date +%s) - T0 )) -lt $WALL ]; do sleep 20; done
kill -0 $WP 2>/dev/null && say "WALL limit reached; emitting partial results" || say "work finished"
emit final
say "idle"; sleep 36000
