# Benchmark & Observability Report — Day 14

**Họ tên:** Dang Duc Cuong
**Ngày chạy:** 25/11/2026
**Môi trường:** Windows 11, AMD Ryzen 5 5600H (12 luồng), RAM 16 GB. Agent và công cụ đo chạy trong WSL2 Ubuntu 26.04, Python 3.11.18. Docker Desktop (Engine 29.4.0): 12 CPU, khoảng 8 GB RAM

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Khi chưa quá tải, p95 khoảng 220 ms. 500 ms chừa khoảng gấp đôi mà người dùng vẫn thấy phản hồi nhanh |
| Error rate `/ask` | < 2 % | Mock LLM lỗi khoảng 1% một cách ngẫu nhiên. 2% chấp nhận mức nền đó nhưng phát hiện khi lỗi tăng gấp đôi |
| Accuracy trên golden dataset | ≥ 85 % | Thấp hơn v2 ban đầu (91.3%) để gate không quá chặt, kèm điều kiện không regression |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.24 | 188.9 | 218.6 | 1694.9 | 1.67% | PASS |
| 10 | 38.29 | 192.0 | 223.6 | 1707.1 | 0.67% | PASS |
| 50 | 117.83 | 198.3 | 248.2 | 1691.3 | 0.33% | PASS |
| 100 | 61.26 | 350.5 | 3454.6 | 3819.8 | 1.67% | FAIL (p95) |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

Không. RPS tăng 4.24 → 38.29 (gấp 9.0 lần khi concurrency gấp 10) → 117.83 (gấp 3.1 lần khi concurrency gấp 5), rồi **giảm** còn 61.26 ở mức 100.

- **Từ 1 tới 50:** phần lớn thời gian là chờ mock LLM (`asyncio.sleep`), nên nhiều request chờ song song được. p50 và p95 tăng ít.
- **Ở 100:** p95 lên 3454.6 ms, vi phạm SLO. Để tìm chỗ nghẽn, tôi chạy riêng hai lần ở mức 100 (`reports/diag_c100.txt`), so latency client đo với `ms` trong log của agent: client p95 là 3384.5 và 3691.0 ms, còn server p95 chỉ 237.9 và 232.2 ms. Agent dùng 370 và 360 ms CPU trong khoảng 5 giây, nên CPU của agent không phải chỗ nghẽn. Vậy phần lớn thời gian mất ở ngoài phần xử lý của agent, trước khi request vào middleware: ở client `load_test.py` hoặc ở giai đoạn thiết lập 100 kết nối. Client và server chạy chung một máy nên phép đo này chưa tách được hai khả năng.
- **Kết luận:** con số ở mức 100 phản ánh giới hạn của cách đo trên máy này, chưa phải giới hạn của agent. Muốn đo giới hạn của agent cần chạy client ở máy khác hoặc dùng Locust nhiều worker.

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 186.5 | 215.3 | 226.5 |
| 0.03 (mặc định) | 248.8 | 228.9 | 1706.1 |
| 0.1 | 325.8 | 1690.6 | 1710.2 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

**p99** nhạy nhất. Với 3% request chậm, avg chỉ tăng từ 186.5 lên 248.8 ms (+62.3 ms) còn p99 nhảy từ 226.5 lên 1706.1 ms; p95 vẫn 228.9 ms vì 3% request chậm nằm ngoài 95% nhanh nhất. Với 10% request chậm, tỉ lệ chậm vượt 5% nên p95 cũng lên 1690.6 ms, trong khi avg mới 325.8 ms.

Average che nhóm người dùng bị chậm: ở mức 0.1, avg 325.8 ms trông như đạt ngưỡng 500 ms, nhưng khoảng 1/10 request mất tới 1.7 giây. Vì vậy SLO nên đặt theo percentile (p95 hoặc p99).

(300 request mỗi lần đo. Bảng 2.2 chạy ở concurrency 20.)

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.1 | 109.0 | 115.2 |
| Tổng cost (USD) | 0.000405 | 0.000760 | 0.000804 |
| Cost / câu đúng (USD) | 0.00040455 | 0.00003619 | 0.00003497 |
| Quality gate | FAIL (≥ 80%) | PASS (≥ 80%) | PASS (≥ 100%) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | token, hết hạn, chữ ký | Không tài liệu nào khớp nên agent trả lời chung chung. Thêm entry `jwt`: so sánh JWT (token có chữ ký số, có hạn) với API key |
| `scaling-03` | cpu, memory, custom metrics | Không tài liệu nào khớp. Thêm entry `hpa` / `kubernetes`: HPA scale theo CPU, memory, custom metrics |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- **Chất lượng:** 4.3% → 91.3% nhờ bước retrieval. Sau khi sửa knowledge base đạt 23/23, 0 câu regression so với `eval_v2.json`. `golden_dataset.jsonl` không bị sửa.
- **Chi phí:** mỗi câu tốn gấp 1.9 lần token (57.1 → 109.0) vì prompt có thêm tài liệu. Nhưng tính trên mỗi câu **đúng**, v2 rẻ hơn khoảng 11 lần (0.00040455 → 0.00003619 USD). Cost / câu che mất việc v1 trả tiền cho câu trả lời sai.
- **Latency:** p50 169.7 → 192.6 ms vì thêm bước retrieval (đo trên 23 câu nên chỉ để tham khảo). Đổi lại mức tăng chất lượng như trên thì đáng.
- **Không dùng eval để kết luận latency:** p95 của lần chạy sau khi sửa là 1560.3 ms chỉ vì 2 trong 23 câu trúng slow request ngẫu nhiên. Với mẫu nhỏ như vậy, 1–2 request chậm là đủ kéo p95. Latency phải đo bằng load test.
- **Giới hạn:** tài liệu được thêm sau khi nhìn câu sai trong golden dataset, nên 100% không có nghĩa là agent đúng mọi câu ngoài thực tế. Cần bổ sung câu hỏi mới vào dataset.

### Quality gate trong CI

Job [`.github/workflows/eval.yml`](.github/workflows/eval.yml) chạy agent v2 rồi eval ở mỗi pull request. `run_eval.py` trả exit code 1 khi accuracy dưới 85% hoặc có câu regression so với `eval_v2_fixed.json`, nên job fail. Khi nhánh `main` bật *Require status checks*, PR không merge được. Trong lần đo này, eval v1 trả exit code 1 và eval v2 trả 0. Job chưa được chạy trên GitHub Actions.

### Exercise 7.1: Metrics của agent

**1. Ví dụ mỗi loại metric** (trích `reports/metrics_sample.txt`):

| Loại | Ví dụ | Ý nghĩa |
|---|---|---|
| Counter | `http_requests_total{method="POST",route="/ask",status="503"} 13.0` | Chỉ tăng, dùng với `rate()` |
| Gauge | `agent_in_flight_requests 0.0` | Lên xuống theo số request đang xử lý |
| Histogram | `http_request_duration_seconds_bucket{le="0.3",method="POST",route="/ask"} 1186.0` | Đếm tích luỹ theo bucket, tính percentile bằng `histogram_quantile()` |

**2. Nếu label `route` dùng URL thật:** mỗi URL lạ (`/wp-admin`, `/.env`, `/a1b2c3`...) tạo thêm time series, riêng histogram còn nhân với số bucket. Bot quét hàng nghìn URL sẽ làm cardinality bùng nổ, Prometheus tốn RAM và chậm dần, và kẻ tấn công có thể cố tình gây ra. Dùng `route.path` thì mọi URL lạ gộp vào một giá trị `unmatched`.

**3. Metric đã thêm:** `agent_question_length_chars` (Histogram) trong `develop/app.py`. Sau lần đo, `agent_question_length_chars_bucket{le="50.0"}` là 1020 trên tổng 1227, tức phần lớn câu hỏi không quá 50 ký tự.

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): [grafana-dashboard.png](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian): [jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (có event `exception`): [jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing**: [prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | 89.4 giây (pending ở 29.3 giây) | Error rate: 1.3% → 18.3% |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` | 146.1 giây (pending ở 28.0 giây) | Latency p95: 296 → 1913 ms (avg chỉ 234 → 622 ms) |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` | 154.3 giây (pending ở 34.2 giây) | Cost burn rate: 0.87 → 11.52 USD/giờ |
| D | `docker pause` 1 instance | `AgentInstanceDown` | 38.1 giây (pending ở 8.1 giây) | Instances up: 2 → 1 |
| E | `AGENT_VERSION=v1` | Không có | Không firing (theo dõi 240 giây) | Phiên bản đang chạy; Tokens/s: 1397 → 716 |

**Cách đo:** `run_chaos.py` đổi `.env`, gọi `docker compose up -d` rồi hỏi Prometheus mỗi 2 giây. Thời gian tính từ ngay trước lệnh đổi. Kết quả gốc: `benchmark-results/chaos_results.jsonl`. Dùng 20 user thay vì 30 vì với 30 user, chi phí nền đã xấp xỉ 2 USD/giờ nên `LLMCostBurnRateHigh` có thể firing sẵn.

**Phân tích:**

- **Từ pending tới firing gần đúng bằng `for` của rule** (sai số do hỏi Prometheus mỗi 2 giây): A 60 giây (`for: 1m`), B 118 giây (`2m`), C 120 giây (`2m`), D 30 giây (`30s`). Phần trước đó (8–34 giây) là thời gian tạo lại container, scrape và đủ dữ liệu để biểu thức vượt ngưỡng.
- **B:** p95 tăng hơn 6 lần còn avg chưa tới 3 lần. Alert theo avg sẽ kém nhạy hơn.
- **C:** số token/giây gần như không đổi (1189 → 1240) nhưng chi phí tăng từ 0.87 lên 11.52 USD/giờ. Mốc 0.87 thấp hơn bình thường vì cửa sổ 5 phút còn lẫn dữ liệu v1 của thí nghiệm E; so với khoảng 1.2 USD/giờ ở các thí nghiệm khác thì tăng gần 10 lần, và cửa sổ này lúc đo cũng chưa chứa trọn 5 phút model mới (đơn giá mỗi token cao hơn khoảng 17 lần). Không theo dõi cost thì không thấy sự cố này, vì error rate vẫn bình thường.
- **D:** Nginx ghi 19 lỗi 504 trên 340 request `/ask` (5.6%) trong lúc instance bị pause, nhưng error rate theo metric của agent chỉ 1.2%. Lỗi 504 do Nginx chờ quá `proxy_read_timeout` nên agent không đếm được. Cần giám sát thêm ở load balancer hoặc synthetic check từ bên ngoài.
- **`AgentInstanceDown` lên pending chốc lát ở A, B, C, E** khi container được tạo lại, có thể vì địa chỉ cũ chưa kịp biến mất khỏi DNS. Nhờ `for: 30s` nên không firing.
- **Hai alert cùng firing:** bật đồng thời A và B, `AgentHighErrorRate` firing sau 89.9 giây và `AgentHighLatencyP95` sau 149.9 giây (ảnh `prometheus-alert-firing.png`).
- **Unit test alert** (`promtool test rules`): SUCCESS.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Sau khi đổi sang v1, dashboard còn trông **tốt hơn**: p95 298 → 198 ms, cost 1.28 → 0.89 USD/giờ. Nhưng chạy eval ngay trên stack đó, accuracy chỉ còn 4.3% (`benchmark-results/eval_chaos_E.json`). Metric hạ tầng đo agent có trả lời nhanh và không lỗi hay không, không đo câu trả lời có đúng hay không.

Cách phát hiện: (1) chạy eval trước mỗi lần deploy và chặn bằng quality gate; (2) chạy eval định kỳ trên bản đang chạy, đưa accuracy thành metric có alert; (3) theo dõi tín hiệu gián tiếp như retrieval hit ratio, token mỗi câu, tỉ lệ người dùng đánh giá kém hoặc hỏi lại; (4) alert khi `agent_info` đổi version ngoài kế hoạch.

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: `b981b371c77513f62264b4cd17479901`
- Tổng thời gian: 1732.7 ms
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (1705.9 ms, 98.5%). `agent.retrieve_context` chỉ 21.8 ms, nên chậm do LLM chứ không phải do retrieval hay code của agent
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-25T14:25:21.544709+00:00", "level": "INFO", "service": "observable-agent", "instance": "84cbd53110b3", "event": "llm_call", "trace_id": "b981b371c77513f62264b4cd17479901", "span_id": "f2dcfb4c9126f48f", "request_id": "721b47dfb24f", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 83, "output_tokens": 44, "cost_usd": 3.9e-05, "llm_ms": 1686.7}
{"ts": "2026-11-25T14:25:21.546202+00:00", "level": "INFO", "service": "observable-agent", "instance": "84cbd53110b3", "event": "http_request", "trace_id": "b981b371c77513f62264b4cd17479901", "span_id": "f2dcfb4c9126f48f", "request_id": "721b47dfb24f", "method": "POST", "route": "/ask", "status": 200, "ms": 1731.7}
```

Trace lỗi `4fea7f936d9476e5669b3f90191a8371` (503, span `chat mock-llm-small` 80.7 ms có event `exception`: *Upstream LLM error: 503 Service Unavailable (mock)*):

```json
{"ts": "2026-11-25T14:27:15.330952+00:00", "level": "INFO", "service": "observable-agent", "instance": "b49acac49aaa", "event": "llm_error", "trace_id": "4fea7f936d9476e5669b3f90191a8371", "span_id": "b9edc06c198e0366", "request_id": "1a0bce89f0b1", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
{"ts": "2026-11-25T14:27:15.332089+00:00", "level": "INFO", "service": "observable-agent", "instance": "b49acac49aaa", "event": "http_request", "trace_id": "4fea7f936d9476e5669b3f90191a8371", "span_id": "b9edc06c198e0366", "request_id": "1a0bce89f0b1", "method": "POST", "route": "/ask", "status": 503, "ms": 104.3}
```

### Exercise 7.4: Đọc dashboard (30 user, 2 instance)

Số lấy từ Prometheus lúc 2026-11-25 21:27:16 (`benchmark-results/ex74_metrics.json`), ảnh `grafana-dashboard.png` chụp ngay trước đó.

1. **p95 và avg:** p95 = 294 ms, avg = 231 ms, p50 = 186 ms, p99 = 1803 ms. Avg cao hơn p50 khoảng 45 ms vì bị khoảng 3% request chậm (1.7 giây) kéo lên. Ở mức 3%, p95 chưa chạm nhóm chậm nên gần avg, còn p99 cho thấy rõ tail latency. p95 trên Grafana là nội suy trong bucket 0.2–0.3 giây, nên cao hơn số của Locust.
2. **Nginx chia đều:** có, 9.33 và 9.31 req/s.
3. **Input tokens/s lớn hơn output:** 1431 so với 751. Mỗi prompt gồm system prompt, tài liệu do retrieval tìm được và câu hỏi, còn câu trả lời ngắn.
4. **`curl http://localhost:8080/metrics`** trả 404: `nginx.conf` chặn `location = /metrics`. Metric lộ route, lưu lượng, model, chi phí nên không public. Prometheus scrape thẳng agent trong mạng nội bộ, không đi qua Nginx.

### Ghi chú khi dựng stack

- `production/Dockerfile` của đề thiếu `PYTHONUSERBASE` nên agent restart liên tục (`ModuleNotFoundError: uvicorn`): HOME của user là `/app` còn package nằm ở `/home/agent/.local`. Đã thêm `ENV PYTHONUSERBASE=/home/agent/.local`.

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 59.83 | 190 | 250 | 1700 | 75 / 7142 (1.05%) |
| 3 | 59.72 | 190 | 220 | 1700 | 86 / 7129 (1.21%) |

(Dòng `/ask` trong `scale_1_stats.csv` và `scale_3_stats.csv`. Failures là 503 do mock LLM.)

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

Rất ít. p50, p99 và RPS gần như không đổi, p95 giảm nhẹ từ 250 xuống 220 ms (mức làm tròn của Locust là 10 ms, mỗi cấu hình chỉ đo một lần nên chưa đủ để kết luận là do scale), dù tải đã được chia đều cho 3 instance (20.5, 21.0, 20.9 req/s theo `scale_metrics.json`).

- **Nút thắt là latency của LLM**, không phải agent. p95 của riêng LLM là 198 ms ở cả hai lần, chiếm phần lớn thời gian request. Thêm instance không làm LLM nhanh hơn.
- **Một instance chưa bão hoà:** chỉ dùng 0.20 core (giới hạn 0.5) ở khoảng 62 req/s. Với 3 instance, mỗi cái dùng 0.07 core. Agent chủ yếu chờ I/O nên một process phục vụ được nhiều request.
- **RPS bị giới hạn bởi số user:** Locust là closed loop, mỗi user nghỉ trung bình 1.25 giây rồi mới gửi tiếp. 100 / (1.25 + 0.215) ≈ 68 req/s cho cả `/ask` và `/health`, gần với tổng 65.9 req/s đo được. Muốn thấy tác dụng của scale phải tăng user tới khi một instance hết CPU.
- Scale vẫn có ích cho độ sẵn sàng: mất một instance vẫn còn instance khác phục vụ.

**Lần đo đầu bị loại:** lệnh `docker compose run locust` không có `--no-deps` đã đưa số agent về `replicas: 2` trong file Compose ngay trước khi đo, nên cả "scale 1" và "scale 3" đều chạy trên 2 instance. Phát hiện nhờ Prometheus (`up`, req/s theo instance) và `docker events`. Số trong bảng là lần đo lại có `--no-deps`, đã kiểm tra đúng 1 và 3 instance.

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. Phải kiểm chứng điều kiện đo trước khi tin kết quả: hai lần đo scale đầu trông hợp lệ nhưng thật ra đều chạy 2 instance.
  2. Average che sự cố, percentile mới cho thấy: với 3% request chậm, avg tăng vài chục ms còn p99 lên 1.7 giây.
  3. Hạ tầng xanh không có nghĩa là chất lượng tốt: v1 nhanh và rẻ hơn nhưng accuracy chỉ 4.3%, không alert nào phát hiện được.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

- Accuracy từ eval chạy định kỳ, alert khi giảm quá 5 điểm % so với bản trước.
- Error rate và latency đo ở Nginx hoặc synthetic check từ bên ngoài, để thấy lỗi 504 mà agent không đếm được.
- Cost theo ngày so với budget, và cost mỗi request, để phát hiện đổi model hoặc prompt phình to.
- Alert khi số instance ít hơn mong đợi: `AgentInstanceDown` dựa vào `up == 0` nên không thấy container đã biến mất khỏi DNS.
- Saturation: CPU, RAM và số request đang xử lý trên mỗi instance.
