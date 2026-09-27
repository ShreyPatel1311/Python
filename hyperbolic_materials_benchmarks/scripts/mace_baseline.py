"""MACE baseline (Batatia et al. 2022, arXiv:2206.07697; package mace-torch) trained from scratch on the exact splits
exported by hyp_force.py (EXPORT_XYZ=1), scored with the same metrics.
Loss 'weighted' with energy_weight = forces_weight = 1 (mace/modules/loss.py: MSE(E/atom) + MSE(F)), same as hyp_force.py
up to a constant. Model: 2 interactions, 32 channels, max_L 1, correlation 3, r_max 5 A; lr 0.01 (MACE default),
plateau factor 0.5 / patience 8, early-stopping patience 25, batch 16, float32.
Usage: mace_baseline.py <dataset> <seed> <max_epochs> [n_structures=3000]   (env DEVICE, OUT as in hyp_force.py)
"""
import json, os, subprocess, sys, time
import numpy as np, torch
from ase.io import read

DS, SEED, MAX_EP = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
N = int(sys.argv[4]) if len(sys.argv) > 4 else 3000
OUT = os.environ.get("OUT", "/tmp/claude-0/data")
DEV = os.environ.get("DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
BIN = os.path.dirname(sys.executable)
f = {k: f"{OUT}/mace_{DS}_{N}_{k}.xyz" for k in ("train", "valid", "test")}
if not os.path.exists(f["test"]):
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hyp_force.py"), DS, "EUC", "0", "0",
                    str(N)], env=dict(os.environ, EXPORT_XYZ="1", OUT=OUT), check=True)
wd = f"{OUT}/mace_{DS}_s{SEED}"
os.makedirs(wd, exist_ok=True)
name = f"mace_{DS}_s{SEED}"
t0 = time.time()
subprocess.run([f"{BIN}/mace_run_train", "--name", name, "--seed", str(SEED), "--train_file", f["train"],
                "--valid_file", f["valid"], "--energy_key", "REF_energy", "--forces_key", "REF_forces", "--E0s", "average",
                "--model", "MACE", "--num_channels", "32", "--max_L", "1", "--r_max", "5.0", "--num_interactions", "2",
                "--correlation", "3", "--loss", "weighted", "--energy_weight", "1", "--forces_weight", "1",
                "--batch_size", "16", "--valid_batch_size", "16", "--lr", "0.01", "--scheduler_patience", "8",
                "--lr_factor", "0.5", "--max_num_epochs", str(MAX_EP), "--patience", "25", "--eval_interval", "1",
                "--default_dtype", "float32", "--device", DEV], cwd=wd, check=True,
               stdout=open(f"{wd}/train.log", "w"), stderr=subprocess.STDOUT)
train_sec = time.time() - t0
# MACE cannot evaluate elements absent from training; score the seen-element test subset (same as hyp_force "test_seen")
from ase.io import write
seen_Z = set(z for a in read(f["train"], ":") for z in a.numbers.tolist())
test_all = read(f["test"], ":")
test_seen = [a for a in test_all if set(a.numbers.tolist()) <= seen_Z]
write(f"{wd}/test_seen.xyz", test_seen, format="extxyz")
subprocess.run([f"{BIN}/mace_eval_configs", "--configs", f"{wd}/test_seen.xyz", "--model", f"{wd}/{name}.model", "--output",
                f"{wd}/pred.xyz", "--device", DEV, "--default_dtype", "float32"], check=True,
               stdout=open(f"{wd}/eval.log", "w"), stderr=subprocess.STDOUT)
ref, pred = read(f"{wd}/test_seen.xyz", ":"), read(f"{wd}/pred.xyz", ":")
ae, af, aff, nf, nff = [], 0.0, 0.0, 0, 0
for r, p in zip(ref, pred):
    n = len(r)
    ae.append(abs(p.info["MACE_energy"] - r.info["REF_energy"]) / n)
    d = np.abs(p.arrays["MACE_forces"] - r.arrays["REF_forces"])
    free = r.arrays["free"].astype(bool) if "free" in r.arrays else np.ones(n, bool)
    af += d.sum(); nf += d.size; aff += d[free].sum(); nff += int(free.sum()) * 3
try:
    model = torch.load(f"{wd}/{name}.model", map_location=torch.device("cpu"), weights_only=False)
except AttributeError:   # torch 2.4.1: '_thread._local' object has no attribute 'map_location'
    model = torch.jit.load(f"{wd}/{name}_compiled.model", map_location="cpu")
epochs = sum(1 for line in open(f"{wd}/train.log") if " INFO: Epoch " in line)
res = dict(dataset=DS, model="MACE", seed=SEED, n_structures=N, n_test=len(test_all), n_test_seen=len(ref),
           n_params=int(sum(p.numel() for p in model.parameters())), device=DEV, epochs_logged=epochs,
           train_sec=round(train_sec, 1), test=None, test_seen=dict(E_MAE_per_atom=float(np.mean(ae)), F_MAE=af / nf, F_MAE_free=aff / max(nff, 1)))
print("RESULT " + json.dumps(res), flush=True)
json.dump(res, open(f"{OUT}/hf_{DS}_MACE_s{SEED}_n{N}.json", "w"))
