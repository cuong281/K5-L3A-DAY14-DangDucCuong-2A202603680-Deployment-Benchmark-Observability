#!/usr/bin/env bash
# CP7: chạy toàn bộ phép đo local. Chạy trong thư mục develop/, đã bật virtualenv.
#   bash run_benchmark.sh measure   # load test + eval v1, v2 (TRƯỚC khi sửa KNOWLEDGE_BASE)
#   bash run_benchmark.sh diagnose  # so latency client và server ở concurrency 100
#   bash run_benchmark.sh fixed     # eval v2 SAU khi sửa KNOWLEDGE_BASE
set -u
OUT=${OUT:-reports}
REQUESTS=${REQUESTS:-300}
PID_V1=""; PID_V2=""
mkdir -p "$OUT"
[ "${1:-}" = diagnose ] && rm -f "$OUT/diag_c100.txt"

stop() { [ -n "$1" ] && kill -TERM "$1" 2>/dev/null && wait "$1" 2>/dev/null; }
cleanup() { stop "$PID_V1"; stop "$PID_V2"; }
trap cleanup EXIT

wait_up() {
  for _ in $(seq 40); do curl -sf -o /dev/null "http://localhost:$1/health" && return 0; sleep 0.5; done
  echo "Agent ở cổng $1 không lên, xem /tmp/agent_$1.log"; exit 1
}
start_v2() { env AGENT_VERSION=v2 PORT=8002 "$@" python app.py >/tmp/agent_8002.log 2>&1 & PID_V2=$!; wait_up 8002; }
load() { python load_test.py --url http://localhost:8002 --requests "$REQUESTS" --concurrency "$1" --out "$OUT/$2"; }

for p in 8001 8002; do
  curl -s -o /dev/null "http://localhost:$p/health" && { echo "Cổng $p đang có server khác, tắt nó trước."; exit 1; }
done

case "${1:-}" in
measure)
  AGENT_VERSION=v1 PORT=8001 python app.py >/tmp/agent_8001.log 2>&1 & PID_V1=$!; wait_up 8001
  start_v2
  for c in 1 10 50 100; do load "$c" "load_v2_c$c.json"; done
  python eval/run_eval.py --url http://localhost:8001 --out "$OUT/eval_v1.json"
  echo "exit code eval v1: $?"
  python eval/run_eval.py --url http://localhost:8002 --baseline "$OUT/eval_v1.json" --out "$OUT/eval_v2.json"
  echo "exit code eval v2: $?"
  curl -s http://localhost:8002/metrics | grep -v '^#' > "$OUT/metrics_sample.txt"
  for rate in 0 0.03 0.1; do
    stop "$PID_V2"; start_v2 MOCK_SLOW_RATE="$rate"; load 20 "load_v2_slow_$rate.json"
  done
  ;;
diagnose)
  for i in 1 2; do
    start_v2
    cpu0=$(awk '{print $14+$15}' "/proc/$PID_V2/stat")
    load 100 "diag_c100_$i.json" >/dev/null
    cpu1=$(awk '{print $14+$15}' "/proc/$PID_V2/stat")
    CPU_MS=$(( (cpu1 - cpu0) * 10 )) python - "$OUT/diag_c100_$i.json" <<'PY' | tee -a "$OUT/diag_c100.txt"
import json, os, sys
r = json.load(open(sys.argv[1]))
ms = sorted(json.loads(l)["ms"] for l in open("/tmp/agent_8002.log")
            if l.startswith("{") and '"http_request"' in l and '"/ask"' in l)
p95 = ms[min(len(ms) - 1, int(len(ms) * 0.95))]
print(f"concurrency=100 duration={r['duration_s']}s rps={r['rps']} "
      f"client_p95={r['latency_ms']['p95']}ms server_p95={p95}ms server_cpu={os.environ['CPU_MS']}ms")
PY
    stop "$PID_V2"; PID_V2=""
  done
  ;;
fixed)
  start_v2
  python eval/run_eval.py --url http://localhost:8002 --min-accuracy 1.0 \
    --baseline "$OUT/eval_v2.json" --out "$OUT/eval_v2_fixed.json"
  echo "exit code eval v2 fixed: $?"
  ;;
*) echo "Dùng: bash run_benchmark.sh measure | diagnose | fixed"; exit 2 ;;
esac
