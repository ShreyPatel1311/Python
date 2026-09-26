#!/usr/bin/env bash
# Vast.ai job (image pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime). SSH is unavailable from the controlling session,
# so results leave the instance only through the container log: at the end a gzip+base64 archive of every result JSON
# is printed between RESULTS_B64_BEGIN / RESULTS_B64_END, then the container idles until destroyed.
# Tracks (run in parallel):
#   A (CPU): task c (new-dataset samples, delta, sensitivity, MACE-MP-0 embeddings + nulls); task d (rebuild old samples,
#            MACE-MP-0 embeddings, HGCN link prediction without / with divergence fixes, GCN baselines, 3 seeds)
#   B (GPU): tasks b+e (hyp_force.py HYP / EUC and mace_baseline.py on MP-ALOE, MatPES, MD22, OC20; 3 seeds)
# Env: BRANCH, STAGES (default "A B"), MAX_EP (150), NSTRUCT (3000), SEEDS3 ("0 1 2"), GPU_PAR (4), WALL (seconds, 18000)
set -uo pipefail
BRANCH=${BRANCH:-claude/material-science-hyperbolic-benchmarks-cfvr0n}
STAGES=${STAGES:-"A B"}; MAX_EP=${MAX_EP:-150}; NSTRUCT=${NSTRUCT:-3000}; SEEDS3=${SEEDS3:-"0 1 2"}
GPU_PAR=${GPU_PAR:-4}; WALL=${WALL:-18000}
D=/tmp/claude-0/data; L=/tmp/claude-0/logs; mkdir -p $D $L
T0=$(date +%s); say() { echo "[$(( $(date +%s) - T0 ))s] $*"; }
say "start $(nvidia-smi -L | head -1) cores=$(nproc)"
apt-get -qq update >/dev/null 2>&1; apt-get -qq install -y git curl unzip xz-utils >/dev/null 2>&1
git clone -q --depth 1 -b "$BRANCH" https://github.com/ShreyPatel1311/Python /root/repo || { say "clone failed"; sleep 36000; }
S=/root/repo/hyperbolic_materials_benchmarks/scripts
git clone -q https://github.com/HazyResearch/hgcn /tmp/claude-0/hgcn && (cd /tmp/claude-0/hgcn && git checkout -q a526385744da25fc880f3da346e17d0fe33817f8 && git apply /root/repo/hyperbolic_materials_benchmarks/hgcn_torch2_compat.patch)
pip install -q numpy scipy numba pandas pyarrow scikit-learn networkx ase pymatgen rdkit fsspec aiohttp mace-torch \
  ase-db-backends > $L/pip.log 2>&1; say "pip exit $? torch=$(python -c 'import torch;print(torch.__version__, torch.cuda.is_available())')"
cd /tmp   # the repo root contains queue.py, which shadows the stdlib module
bash $S/download_data.sh old new > $L/download.log 2>&1; say "download exit $? $(du -sh $D | cut -f1)"
export OMP_NUM_THREADS=4 NUMBA_NUM_THREADS=8

trackA() {
  python $S/load_samples_new.py 2000 > $L/samples_new.log 2>&1; say "A samples_new exit $?"
  ( SAMPLES=$D/samples_new.pkl TAG=_new python $S/run_delta.py > $L/delta_new.log 2>&1; say "A delta_new exit $?" ) &
  python $S/sensitivity_new.py > $L/sens_new.log 2>&1; say "A sensitivity_new exit $?"
  DEVICE=cuda SAMPLES=$D/samples_new.pkl TAG=_new SKIP_REFS=1 python -W ignore $S/embed_mace.py > $L/mace_new.log 2>&1; say "A embed_new exit $?"
  ( SAMPLES=$D/samples_new.pkl TAG=_new python $S/null_models.py > $L/null_new.log 2>&1; say "A null_new exit $?" ) &
  python $S/load_samples.py > $L/samples_old.log 2>&1; say "A samples_old exit $?"
  python $S/fix_tensor_samples.py >> $L/samples_old.log 2>&1; say "A fix_tensor exit $?"
  DEVICE=cuda TAG=_rebuild SKIP_REFS=1 python -W ignore $S/embed_mace.py > $L/mace_old.log 2>&1; say "A embed_old exit $?"
  for cfg in "HGCN none" "HGCN clip" "HGCN clip+cbound" "GCN none"; do
    set -- $cfg
    ( FIX=$2 SEEDS=0,1,2 python -W ignore $S/hgcn_sweep.py $1 1 all > $L/sweep_$1_$2.log 2>&1; say "A sweep $1 $2 exit $?" ) &
  done
  wait
}

trackB() {
  for ds in MP-ALOE MatPES MD22 OC20; do   # build caches + MACE splits once per dataset
    DEVICE=cuda OUT=$D python -W ignore $S/hyp_force.py $ds EUC 0 0 $NSTRUCT > $L/cache_$ds.log 2>&1
    DEVICE=cuda OUT=$D EXPORT_XYZ=1 python -W ignore $S/hyp_force.py $ds EUC 0 0 $NSTRUCT >> $L/cache_$ds.log 2>&1
    say "B cache $ds exit $?"
  done
  rm -f $D/hf_*_EUC_s0_n*.json
  for s in $SEEDS3; do for ds in MP-ALOE MatPES MD22 OC20; do
    for m in HYP EUC; do echo "hyp_force.py $ds $m $s $MAX_EP $NSTRUCT"; done
    echo "mace_baseline.py $ds $s $MAX_EP $NSTRUCT"
  done; done > $L/gpu_jobs.txt
  cat $L/gpu_jobs.txt | xargs -P $GPU_PAR -I{} bash -c 'set -- {}; DEVICE=cuda OUT='$D' python -W ignore '$S'/$* > '$L'/job_$(echo "$*" | tr " /" "__").log 2>&1; echo "[B] $* exit $?"'
  say "B done"
}

PIDS=""
for st in $STAGES; do
  case $st in A) trackA & PIDS="$PIDS $!" ;; B) trackB & PIDS="$PIDS $!" ;; esac
done
alive() { for p in $PIDS; do kill -0 $p 2>/dev/null && return 0; done; return 1; }
while alive && [ $(( $(date +%s) - T0 )) -lt $WALL ]; do sleep 30; done
alive && say "WALL limit reached; emitting partial results" || say "tracks finished"
python - <<'EOF'
import base64, glob, gzip, io, json, os, tarfile
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tf:
    for f in sorted(glob.glob("/tmp/claude-0/data/*.json") + glob.glob("/tmp/claude-0/logs/*.log")):
        if f.endswith(("pip.log", "download.log")) or os.path.getsize(f) > 20_000_000:
            continue
        tf.add(f, arcname=f.split("/claude-0/")[1])
b = base64.b64encode(buf.getvalue()).decode()
print("RESULTS_B64_BEGIN", len(b), flush=True)
for i in range(0, len(b), 4000):
    print("B64", i // 4000, b[i:i + 4000], flush=True)
print("RESULTS_B64_END", flush=True)
EOF
say "idle"; sleep 36000
