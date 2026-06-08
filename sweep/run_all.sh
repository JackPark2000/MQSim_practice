#!/usr/bin/env bash
set -u
JOBS=4
NAMES=(
  baseline
  sw_occ_70 sw_occ_80 sw_occ_90 sw_occ_95
  sw_ws_50 sw_ws_20 sw_ws_10 sw_ws_5
  sw_thr_0p005 sw_thr_0p01 sw_thr_0p025 sw_thr_0p05
  sw_op_0p05 sw_op_0p03 sw_op_0p02 sw_op_0p01
)
ROOT=$(pwd)
mkdir -p sweep/logs
printf "%s\n" "${NAMES[@]}" | xargs -I {} -P "$JOBS" bash -c '
name="$0"; root="$1"
rd="$root/sweep/runs/$name"
log="$root/sweep/logs/${name}.log"
( cd "$rd" && /usr/bin/time -f "REAL=%e USER=%U SYS=%S MAXRSS=%M_KB" ./MQSim -i ssd.xml -w wl.xml ) > "$log" 2>&1
rc=$?
echo "DONE $name (exit=$rc)"
' {} "$ROOT"
