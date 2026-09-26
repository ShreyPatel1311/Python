#!/usr/bin/env bash
# Download datasets into /tmp/claude-0/data (paths the scripts expect). Usage: download_data.sh <item>...
# items: mpaloe matpes mptrj mpcoll cdvae qm9 md22 md22ac rmd17 oc20 omat jarvis   (old = the first six; new = the last five)
# mpcoll: the MP 2025-09-25 build collections elasticity / dielectric / piezoelectric are jsonl.gz partitions; they are
# concatenated in S3 key order into <collection>/data.parquet (material_id, structure JSON, symmetry, deprecated),
# the layout load_samples.py reads.
set -euo pipefail
D=/tmp/claude-0/data; mkdir -p "$D"; cd "$D"
PY=${PY:-python}
ITEMS=" $* "; ITEMS=${ITEMS/ old / mpaloe matpes mptrj mpcoll cdvae qm9 }; ITEMS=${ITEMS/ new / md22 rmd17 oc20 omat jarvis }
has() { [[ "$ITEMS" == *" $1 "* ]]; }
get() { [ -s "$2" ] || curl -sSL --retry 4 -o "$2" "$1"; }
C=https://materialsproject-contribs.s3.amazonaws.com
F=https://dl.fbaipublicfiles.com/opencatalystproject/data
has mpaloe && get "$C/MP_ALOE_2025/format=parquet/MP-ALOE-2025.parquet" mpaloe.parquet &
has matpes && get "$C/MatPES_2025_1/format=parquet/MatPES-2025.1.parquet" matpes.parquet &
has mptrj && get "$C/MPtrj_2022_9/format=parquet/MPtrj-2022.9_full.parquet" mptrj.parquet &
has qm9 && get https://deepchemdata.s3-us-west-1.amazonaws.com/datasets/gdb9.tar.gz gdb9.tar.gz &
if has cdvae; then
  for s in mp_20 perov_5 carbon_24; do mkdir -p $s; for sp in train val test; do
    get "https://raw.githubusercontent.com/txie-93/cdvae/main/data/$s/$sp.csv" $s/$sp.csv; done; done
fi
if has mpcoll; then
  $PY - <<'EOF'
import gzip, io, json, re, urllib.request, os
import pyarrow as pa, pyarrow.parquet as pq
B = "https://materialsproject-build.s3.amazonaws.com"
for coll in ("elasticity", "dielectric", "piezoelectric"):
    if os.path.exists(f"{coll}/data.parquet"):
        continue
    s = urllib.request.urlopen(f"{B}/?list-type=2&prefix=collections/2025-09-25/{coll}/").read().decode()
    assert "<IsTruncated>false" in s
    keys = sorted(k for k in re.findall("<Key>([^<]*)", s) if k.endswith(".jsonl.gz") and "manifest" not in k)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(16) as ex:   # order preserved by map
        blobs = list(ex.map(lambda k: urllib.request.urlopen(f"{B}/{k}").read(), keys))
    rows = []
    for blob in blobs:
        for line in gzip.GzipFile(fileobj=io.BytesIO(blob)):
            d = json.loads(line)
            rows.append(dict(material_id=d["material_id"], structure=json.dumps(d.get("structure")),
                             symmetry=d.get("symmetry"), deprecated=bool(d.get("deprecated"))))
    os.makedirs(coll, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), f"{coll}/data.parquet")
    print(coll, len(keys), "partitions,", len(rows), "rows", flush=True)
EOF
fi
MD22="Ac-Ala3-NHMe DHA stachyose AT-AT AT-AT-CG-CG buckyball-catcher double-walled_nanotube"
has md22ac && MD22="Ac-Ala3-NHMe"
if has md22 || has md22ac; then
  for m in $MD22; do get "https://sgdml.org/secure_proxy.php?file=repo/datasets/md22_$m.npz" md22_$m.npz & done
fi
if has rmd17; then   # figshare article 12672038 per-molecule npz file ids
  for p in ethanol:62265733 azobenzene:62265754 toluene:62265742 aspirin:62265757 benzene:62265739 \
           naphthalene:62265751 malonaldehyde:62265736 paracetamol:62265760 salicylic:62265748 uracil:62265745; do
    get "https://ndownloader.figshare.com/files/${p#*:}" rmd17_${p%%:*}.npz & done
fi
has oc20 && get $F/s2ef_train_200K.tar s2ef_train_200K.tar &
if has omat; then
  for s in rattled-300-subsampled aimd-from-PBE-3000-nvt; do
    ( get "$F/omat/241220/omat/val/$s.tar.gz" omat_val_$s.tar.gz && { [ -d $s ] || tar xzf omat_val_$s.tar.gz; } ) & done
fi
has jarvis && ( get https://ndownloader.figshare.com/files/64391379 jarvis_dft_3d.zip && unzip -o -q jarvis_dft_3d.zip ) &
wait
ls -la "$D"
