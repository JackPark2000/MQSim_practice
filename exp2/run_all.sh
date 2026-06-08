#!/usr/bin/env bash
set -u
JOBS=${JOBS:-6}
ROOT=$(pwd)
mkdir -p exp2/logs
# Read TO_RUN list from JSON
python3 -c "import json; print('\n'.join(json.load(open('exp2/to_run.json'))))" \
| xargs -I {} -P "$JOBS" bash -c '
name="$0"; root="$1"
rd="$root/exp2/runs/$name"
log="$root/exp2/logs/${name}.log"
( cd "$rd" && /usr/bin/time -f "REAL=%e USER=%U SYS=%S MAXRSS=%M_KB" ./MQSim -i ssd.xml -w wl.xml ) > "$log" 2>&1
rc=$?
echo "DONE $name (exit=$rc)"
' {} "$ROOT"
