"""
CP8: thí nghiệm phá hệ thống A–E, đo thời gian từ lúc đổi cấu hình tới lúc alert firing.

Chạy trong thư mục production/, stack đã bật với -p k5-day14-observability:
    python run_chaos.py              # A B D E C, rồi AB (giữ 2 alert firing để chụp ảnh)
    python run_chaos.py D            # chỉ chạy các thí nghiệm được liệt kê

Dùng 20 user thay vì 30: với 30 user, chi phí nền đã xấp xỉ 2 USD/giờ nên
LLMCostBurnRateHigh firing sẵn và không đo được thí nghiệm C.
"""
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT = "k5-day14-observability"
USERS = 20
PROM = "http://localhost:9090/api/v1"
LOAD = "day14-chaos-load"
OUT = Path("benchmark-results/chaos_results.jsonl")
DEFAULT_ENV = Path(".env.example").read_text(encoding="utf-8")

EXPERIMENTS = {
    "A": ({"MOCK_ERROR_RATE": "0.2"}, ["AgentHighErrorRate"]),
    "B": ({"MOCK_SLOW_RATE": "0.3"}, ["AgentHighLatencyP95"]),
    "C": ({"LLM_MODEL": "mock-llm-large"}, ["LLMCostBurnRateHigh"]),
    "D": (None, ["AgentInstanceDown"]),
    "E": ({"AGENT_VERSION": "v1"}, []),
    "AB": ({"MOCK_ERROR_RATE": "0.2", "MOCK_SLOW_RATE": "0.3"},
           ["AgentHighErrorRate", "AgentHighLatencyP95"]),
}
E_WATCH_SECONDS = 240


def sh(*cmd, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"Lệnh lỗi: {' '.join(cmd)}\n{r.stderr[-800:]}")
    return r.stdout + r.stderr


def compose(*args, check=True):
    return sh("docker", "compose", "-p", PROJECT, *args, check=check)


def prom(path, **params):
    url = f"{PROM}/{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.load(resp)["data"]


def value(expr):
    result = prom("query", query=expr)["result"]
    return round(float(result[0]["value"][1]), 4) if result else None


def alerts():
    """{tên alert: trạng thái}; firing được ưu tiên nếu có nhiều instance."""
    states = {}
    for a in prom("alerts")["alerts"]:
        name = a["labels"]["alertname"]
        if states.get(name) != "firing":
            states[name] = a["state"]
    return states


def snapshot():
    sel = '{job="agent",route="/ask"}'
    err = '{job="agent",route="/ask",status=~"5.."}'
    hist = f"sum by (le) (rate(http_request_duration_seconds_bucket{sel}[1m]))"
    return {
        "rps": value(f"sum(rate(http_requests_total{sel}[1m]))"),
        "error_rate": value(f"sum(rate(http_requests_total{err}[1m])) / sum(rate(http_requests_total{sel}[1m]))"),
        "p95_s": value(f"histogram_quantile(0.95, {hist})"),
        "p99_s": value(f"histogram_quantile(0.99, {hist})"),
        "avg_s": value(f"sum(rate(http_request_duration_seconds_sum{sel}[1m])) / "
                       f"sum(rate(http_request_duration_seconds_count{sel}[1m]))"),
        "cost_usd_per_hour": value('sum(rate(llm_cost_usd_total{job="agent"}[5m])) * 3600'),
        "tokens_per_s": value('sum(rate(llm_tokens_total{job="agent"}[1m]))'),
        "instances_up": value('sum(up{job="agent"})'),
        "instances_down": value('count(up{job="agent"} == 0)'),
    }


def apply_env(overrides):
    lines = []
    for line in DEFAULT_ENV.splitlines():
        key = line.split("=", 1)[0]
        lines.append(f"{key}={overrides[key]}" if key in overrides else line)
    Path(".env").write_text("\n".join(lines) + "\n", encoding="utf-8")
    compose("up", "-d", "--scale", "agent=2")


def start_load():
    sh("docker", "rm", "-f", LOAD, check=False)
    # --no-deps: nếu thiếu, `compose run` đưa số agent về replicas trong file Compose
    compose("run", "-d", "--rm", "--no-deps", "--name", LOAD, "locust", "-f", "/mnt/locust/locustfile.py",
            "--host", "http://nginx", "--headless", "-u", str(USERS), "-r", "5", "-t", "60m")


def wait_quiet(limit=600):
    """Chờ hết alert (cả pending) trước khi bắt đầu thí nghiệm mới."""
    start = time.time()
    while time.time() - start < limit:
        active = alerts()
        if not active:
            return
        print(f"    chờ alert cũ tắt: {active}", flush=True)
        time.sleep(15)
    raise SystemExit("Alert cũ không tắt, dừng lại")


def clock():
    return time.strftime("%H:%M:%S")


def nginx_statuses(since):
    logs = sh("docker", "logs", "--since", str(int(since)), f"{PROJECT}-nginx-1", check=False)
    counts = {}
    for code in re.findall(r'"POST /ask[^"]*" (\d{3}) ', logs):  # chỉ access log
        counts[code] = counts.get(code, 0) + 1
    return counts


def run(name):
    overrides, expected = EXPERIMENTS[name]
    print(f"\n=== Thí nghiệm {name}: {overrides or 'docker pause 1 instance'}", flush=True)
    wait_quiet()
    before = snapshot()
    t0 = time.time()
    record = {"experiment": name, "change": overrides or {"docker": "pause agent-2"},
              "users": USERS, "t0": clock(), "before": before, "alerts": {}}
    paused = f"{PROJECT}-agent-2"
    if overrides is None:
        sh("docker", "pause", paused)
    else:
        apply_env(overrides)
    record["apply_seconds"] = round(time.time() - t0, 1)

    limit = E_WATCH_SECONDS if not expected else 600
    while time.time() - t0 < limit:
        for alert, state in alerts().items():
            seen = record["alerts"].setdefault(alert, {})
            if state not in seen:
                seen[state] = round(time.time() - t0, 1)
                print(f"    {clock()} {alert}: {state} sau {seen[state]}s", flush=True)
        if expected and all("firing" in record["alerts"].get(a, {}) for a in expected):
            break
        time.sleep(2)
    record["after"] = snapshot()

    if name == "E":
        print("    chạy eval trên stack đang chạy v1...", flush=True)
        out = Path("benchmark-results/eval_chaos_E.json")
        sh(sys.executable, "../develop/eval/run_eval.py", "--url", "http://localhost:8080",
           "--api-key", "day14-lab-key", "--out", str(out), check=False)
        record["eval_accuracy"] = json.loads(out.read_text(encoding="utf-8"))["accuracy"]
    if name == "D":
        record["nginx_status_codes"] = nginx_statuses(t0)
        sh("docker", "unpause", paused)
    if name == "AB":
        print("\n>>> HAI ALERT ĐANG FIRING. Chụp http://localhost:9090/alerts "
              "→ screenshots/prometheus-alert-firing.png", flush=True)
        input(">>> Chụp xong thì nhấn Enter để trả cấu hình về mặc định... ")
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print("    " + json.dumps(record, ensure_ascii=False), flush=True)
    if overrides is not None:
        apply_env({})


def main():
    names = sys.argv[1:] or ["A", "B", "D", "E", "C", "AB"]
    unknown = [n for n in names if n not in EXPERIMENTS]
    if unknown:
        raise SystemExit(f"Không có thí nghiệm: {unknown}")
    print("Bật stack mặc định, 2 agent, tạo tải nền...", flush=True)
    apply_env({})
    start_load()
    try:
        time.sleep(90)  # đủ dữ liệu cho cửa sổ rate 1 phút
        for name in names:
            run(name)
            time.sleep(60)
    finally:
        sh("docker", "unpause", f"{PROJECT}-agent-2", check=False)
        sh("docker", "rm", "-f", LOAD, check=False)
        apply_env({})
        print("\nĐã tắt tải và trả cấu hình về mặc định.", flush=True)


if __name__ == "__main__":
    main()
