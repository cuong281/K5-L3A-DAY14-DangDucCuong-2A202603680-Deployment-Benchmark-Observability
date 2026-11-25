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

- [ ] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals)
- [ ] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian)
- [ ] Một trace lỗi trong Jaeger (có event `exception`)
- [ ] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | | | |
| B | `MOCK_SLOW_RATE=0.3` | | | |
| C | `LLM_MODEL=mock-llm-large` | | | |
| D | `docker pause` 1 instance | | | |
| E | `AGENT_VERSION=v1` | | | |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

...

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: ...
- Tổng thời gian: ... ms
- Span chiếm nhiều thời gian nhất: ... (... ms, ...%)
- Dòng log tương ứng (grep theo `trace_id`):

```json

```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | | | | | |
| 3 | | | | | |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

...

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. ...
  2. ...
  3. ...
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

...
