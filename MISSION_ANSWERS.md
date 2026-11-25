# Day 14 Lab - Mission Answers

Môi trường: Windows 11, WSL2 (Ubuntu 26.04), Python 3.11.18, Docker 29.4.0, Docker Compose v5.1.1.

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

File: `01-localhost-vs-production/develop/app.py`

| # | Dòng | Anti-pattern | Hậu quả |
|---|---|---|---|
| 1 | 17–18 | Hardcode API key và chuỗi kết nối database (có mật khẩu) | Push lên Git là lộ; xoá file vẫn còn trong lịch sử commit, phải thu hồi và đổi key |
| 2 | 34 | In API key ra log | Ai đọc được log cũng lấy được key, kể cả khi key không còn nằm trong code |
| 3 | 21–22 | Config cố định trong code (`DEBUG`, `MAX_TOKENS`) | Muốn đổi giữa dev và production phải sửa code và deploy lại |
| 4 | 33–38, 48 | Dùng `print()` thay cho logging | Không có mức log, thời gian hay cấu trúc để lọc và cảnh báo |
| 5 | toàn file | Không có `/health` và `/ready` | Platform không biết khi nào cần restart hoặc ngừng gửi traffic |
| 6 | 51 | Bind `host="localhost"` | Trong container, request từ bên ngoài không vào được |
| 7 | 52 | Cố định `port=8000` | Railway/Render cấp cổng qua biến `PORT`, app nghe sai cổng |
| 8 | 53 | `reload=True` | Chạy thêm process theo dõi file, chỉ phù hợp lúc phát triển |
| 9 | toàn file | Không xử lý việc tắt ứng dụng | Không có bước dọn dẹp hoặc báo chưa sẵn sàng trước khi process dừng |

### Exercise 1.2: Chạy bản develop

Bản develop nhận `question` qua query string.

```console
$ curl -i -X POST "http://localhost:8000/ask?question=Hello"
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:19:39 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}

$ curl -i http://localhost:8000/health
HTTP/1.1 404 Not Found
date: Wed, 25 Nov 2026 08:18:24 GMT
server: uvicorn
content-length: 22
content-type: application/json

{"detail":"Not Found"}
```

Log của server in luôn API key (key giả có sẵn trong đề):

```text
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
[DEBUG] Response: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.
```

App trả lời được nhưng chưa sẵn sàng cho production: lộ secret qua log, không có health check, chỉ nghe ở localhost.

### Exercise 1.3: Comparison table

| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| Config | Hardcode (dòng 17–22) | `config.py` đọc biến môi trường | Cùng một image chạy được ở dev, staging, production. Secret không nằm trong code. Thiếu `AGENT_API_KEY` ở production thì app dừng ngay khi khởi động (`config.py:43`) thay vì chạy với cấu hình sai |
| Health check | Không có, `/health` trả 404 | `/health` (dòng 135) và `/ready` (dòng 152) | `/health` cho biết process còn sống để quyết định restart. `/ready` cho biết đã nhận traffic được chưa, nên lúc khởi động hoặc sắp tắt thì trả 503 mà không bị restart |
| Logging | `print()`, in cả API key | Log theo mẫu JSON, chỉ ghi độ dài câu hỏi | Log có cấu trúc thì lọc, tìm và cảnh báo tự động được. Không ghi secret và nội dung nhạy cảm |
| Shutdown | Không xử lý | Lifespan đặt `is_ready = False` (dòng 64) và có handler SIGTERM (dòng 180) | Platform gửi SIGTERM mỗi lần deploy. App cần xử lý xong request đang chạy và đóng kết nối trước khi thoát |
| Host / Port | `localhost:8000` cố định | `0.0.0.0` và biến `PORT` | Container nhận được request từ ngoài, chạy đúng cổng platform cấp |
| Reload | Luôn bật | Chỉ khi `DEBUG=true` | Không chạy process theo dõi file ở production |

Kết quả chạy bản production:

```console
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:24:34 GMT
server: uvicorn
content-length: 167
content-type: application/json

{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","model":"gpt-4o-mini"}

$ curl -i http://localhost:8000/health
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:24:39 GMT
server: uvicorn
content-length: 130
content-type: application/json

{"status":"ok","uptime_seconds":14.7,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T08:24:40.060978+00:00"}

$ curl -i http://localhost:8000/ready
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:24:46 GMT
server: uvicorn
content-length: 14
content-type: application/json

{"ready":true}
```

Log khi nhận SIGTERM (chạy với `OPENAI_API_KEY=mock-not-a-real-key`, tắt bằng `pkill -TERM -f "python app.py"`):

```text
{"time":"2026-11-25 15:26:22,000","level":"INFO","msg":"{"event": "agent_request", "question_length": 5, "client_ip": "127.0.0.1"}"}
{"time":"2026-11-25 15:26:22,104","level":"INFO","msg":"{"event": "agent_response", "response_length": 66}"}
INFO:     127.0.0.1:36334 - "POST /ask HTTP/1.1" 200 OK
INFO:     Shutting down
INFO:     Waiting for application shutdown.
{"time":"2026-11-25 15:26:30,945","level":"INFO","msg":"Agent shutting down gracefully — finishing in-flight requests..."}
{"time":"2026-11-25 15:26:31,046","level":"INFO","msg":"Shutdown complete"}
INFO:     Application shutdown complete.
INFO:     Finished server process [1455]
{"time":"2026-11-25 15:26:31,046","level":"INFO","msg":"Received SIGTERM — initiating graceful shutdown"}
```

**Những điểm bản production mẫu vẫn chưa tốt:**

1. Lần chạy đầu không có dòng log JSON nào. `config.py:45` gọi `logging.warning()` lúc import (`app.py:24`), trước `logging.basicConfig()` ở `app.py:28`. Lệnh `warning` tự cấu hình root logger, nên `basicConfig` không còn tác dụng và log INFO bị bỏ. Khi có `OPENAI_API_KEY` thì không có warning và log JSON hiện đủ.
2. Trường `msg` chứa chuỗi JSON lồng không escape dấu nháy, nên dòng `agent_request` ở trên không phải JSON hợp lệ.
3. Code không gọi `load_dotenv()`, nên file `.env` không được nạp khi chạy `python app.py`.

Part 6 cần tránh hai lỗi đầu: cấu hình logging sớm và dùng formatter tạo cả dòng log bằng `json.dumps`.

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

File: `02-docker/develop/Dockerfile`

1. **Base image:** `python:3.11`, bản Python đầy đủ trên Debian, không phải `slim`.
2. **Working directory:** `/app`. Các lệnh `COPY`, `RUN`, `CMD` phía sau dùng thư mục này làm gốc.
3. **Vì sao COPY `requirements.txt` trước:** Docker cache theo từng layer. Khi chỉ sửa code, layer `pip install` phía trước không đổi nên được dùng lại. Nếu `COPY . .` đứng trước, mỗi lần sửa code đều phải cài lại toàn bộ thư viện.
4. **CMD và ENTRYPOINT:** `CMD` là lệnh mặc định, bị thay thế khi truyền lệnh khác sau tên image trong `docker run`. `ENTRYPOINT` là chương trình cố định của container, tham số sau tên image được nối thêm vào (muốn đổi phải dùng `--entrypoint`). Dùng cả hai thì `CMD` trở thành tham số mặc định cho `ENTRYPOINT`.

### Exercise 2.2: Build và run

Build từ gốc repo vì Dockerfile `COPY` theo đường dẫn tính từ gốc.

```console
$ docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
$ docker run --rm --name day14-dev -p 8000:8000 my-agent:develop
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)

$ curl -i -X POST "http://localhost:8000/ask?question=What%20is%20Docker"
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:53:51 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

### Exercise 2.3: Image size comparison

```console
$ docker images my-agent
IMAGE               ID             DISK USAGE   CONTENT SIZE
my-agent:advanced   cbc82055d9be        240MB         57.4MB
my-agent:develop    4371cbca4708       1.67GB          426MB
```

| | Develop | Production | Difference |
|---|---:|---:|---:|
| Disk usage (đã bung ra đĩa) | 1.67 GB | 240 MB | giảm 85.6% |
| Content size (dữ liệu nén) | 426 MB | 57.4 MB | giảm 86.5% |

- **Stage 1 (`builder`):** từ `python:3.11-slim`, cài `gcc`, `libpq-dev` rồi `pip install --user` vào `/root/.local`.
- **Stage 2 (`runtime`):** bắt đầu lại từ `python:3.11-slim`, chỉ `COPY --from=builder` phần thư viện đã cài, thêm code, chạy bằng user `appuser`.
- **Vì sao nhỏ hơn:** base `slim` thay cho bản đầy đủ, và công cụ build (`gcc`, `libpq-dev`) ở lại stage 1, không có trong image cuối. Hai yếu tố này cùng góp vào mức giảm, số đo trên không tách riêng từng phần.

### Exercise 2.4: Docker Compose stack

```text
            Client (máy host)
                  │  :80
                  ▼
        ┌───────────────────┐
        │ nginx             │  service duy nhất mở cổng ra host (80, 443)
        │ reverse proxy     │  rate limit 10 req/s mỗi IP
        └─────────┬─────────┘
                  │  http://agent:8000
                  ▼
        ┌───────────────────┐
        │ agent (FastAPI)   │  chỉ mở 8000 trong mạng nội bộ
        └────┬─────────┬────┘
             │         │       REDIS_URL, QDRANT_URL
             ▼         ▼
     ┌────────────┐ ┌────────────┐
     │ redis:6379 │ │ qdrant:6333│
     └────────────┘ └────────────┘
     Tất cả nằm trong mạng bridge "internal"
```

```console
$ docker compose -p k5-day14-docker up -d --build
$ docker compose -p k5-day14-docker ps
NAME                       IMAGE                   SERVICE   STATUS                        PORTS
k5-day14-docker-agent-1    k5-day14-docker-agent   agent     Up About a minute (healthy)   8000/tcp
k5-day14-docker-nginx-1    nginx:alpine            nginx     Up About a minute             0.0.0.0:80->80/tcp, [::]:80->80/tcp, 0.0.0.0:443->443/tcp, [::]:443->443/tcp
k5-day14-docker-qdrant-1   qdrant/qdrant:v1.9.0    qdrant    Up About a minute (healthy)   6333-6334/tcp
k5-day14-docker-redis-1    redis:7-alpine          redis     Up About a minute (healthy)   6379/tcp
```

**Services và cách giao tiếp:** 4 service `agent`, `redis`, `qdrant`, `nginx` gọi nhau bằng tên service qua DNS của Docker. `agent` đợi `redis` và `qdrant` healthy rồi mới khởi động (`depends_on` + `service_healthy`). Bên ngoài chỉ vào được qua Nginx.

Kết quả test qua Nginx (`Server: nginx`):

```console
$ curl -i http://localhost/health
HTTP/1.1 200 OK
Server: nginx
Date: Wed, 25 Nov 2026 08:56:31 GMT
Content-Type: application/json
Content-Length: 96
Connection: keep-alive
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":45.8,"version":"2.0.0","timestamp":"2026-11-25T08:56:31.561802"}

$ curl -i -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question": "Explain microservices"}'
HTTP/1.1 200 OK
Server: nginx
Date: Wed, 25 Nov 2026 08:56:39 GMT
Content-Type: application/json
Content-Length: 103
Connection: keep-alive
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

**Nhận xét:** stack khai báo `REDIS_URL` và `QDRANT_URL`, nhưng `main.py` của bài mẫu chưa dùng hai service này. Cổng 443 được mở nhưng `nginx.conf` chỉ cấu hình `listen 80`, nên chưa có HTTPS.

## Part 4: API Security

### Exercise 4.1-4.3: Test results

**4.1 API key** (`04-api-gateway/develop`, bật bằng `AGENT_API_KEY=secret-key-123 python app.py`, key mẫu của đề)

```console
# Thiếu key
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 401 Unauthorized
date: Wed, 25 Nov 2026 08:59:52 GMT
server: uvicorn
content-length: 67
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# Sai key
$ curl -i -X POST http://localhost:8000/ask -H "X-API-Key: wrong-key" -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 403 Forbidden
date: Wed, 25 Nov 2026 08:59:56 GMT
server: uvicorn
content-length: 29
content-type: application/json

{"detail":"Invalid API key."}

# Đúng key
$ curl -i -X POST http://localhost:8000/ask -H "X-API-Key: ***" -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 09:07:22 GMT
server: uvicorn
content-length: 122
content-type: application/json

{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

- **Key được check ở đâu:** dependency `verify_api_key` (`app.py:39`), gắn vào `/ask` bằng `Depends` (`app.py:70`). Key đúng lấy từ biến môi trường `AGENT_API_KEY` (`app.py:35`).
- **Sai key:** thiếu key trả 401, sai key trả 403, hàm `/ask` không được chạy nên không gọi LLM. Part 6 yêu cầu 401 cho cả hai trường hợp.
- **Rotate key:** đổi `AGENT_API_KEY` trên nền tảng rồi restart app. App chỉ giữ một key nên client dùng key cũ bị chặn ngay. Muốn đổi không gián đoạn thì cho phép hai key cùng hợp lệ trong thời gian chuyển đổi rồi bỏ key cũ.

**4.2 JWT** (`04-api-gateway/production`)

Token lấy ở `POST /auth/token` với tài khoản `student`, lưu vào biến `TOKEN`, không in ra màn hình.

```console
# Không token
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question": "Explain JWT"}'
HTTP/1.1 401 Unauthorized
date: Wed, 25 Nov 2026 09:02:27 GMT
server: uvicorn
www-authenticate: Bearer
content-length: 76
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}

# Có token
$ curl -i -X POST http://localhost:8000/ask -H "Authorization: Bearer ***" -H "Content-Type: application/json" -d '{"question": "Explain JWT"}'
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 09:02:39 GMT
server: uvicorn
content-length: 215
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Explain JWT","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","usage":{"requests_remaining":9,"budget_remaining_usd":2.1e-05}}
```

**Luồng JWT:** client gửi username/password một lần, server trả token đã ký (HS256) chứa `sub`, `role`, `iat`, `exp` (60 phút). Mỗi request sau gửi `Authorization: Bearer <token>`. Server kiểm tra chữ ký và hạn dùng bằng secret, không cần tra database. Token hết hạn trả 401, token sai chữ ký trả 403.

**4.3 Rate limiting**

```console
$ for i in {1..12}; do ... curl -s -o /dev/null -w '%{http_code}\n' ... ; done
Request  1: 200
Request  2: 200
Request  3: 200
Request  4: 200
Request  5: 200
Request  6: 200
Request  7: 200
Request  8: 200
Request  9: 200
Request 10: 429
Request 11: 429
Request 12: 429

$ curl -i -X POST http://localhost:8000/ask -H "Authorization: Bearer ***" -H "Content-Type: application/json" -d '{"question": "Test"}'
HTTP/1.1 429 Too Many Requests
date: Wed, 25 Nov 2026 09:03:29 GMT
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795597469
retry-after: 10
content-length: 98
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":10}}
```

- **Algorithm:** sliding window. Mỗi user có một `deque` timestamp, bỏ các mốc cũ hơn 60 giây rồi đếm.
- **Limit:** user 10 request/phút, admin 100 request/phút (`rate_limiter.py:86-87`).
- **Vì sao 429 từ request 10:** request ở bài 4.2 (09:02:39) vẫn nằm trong cửa sổ 60 giây nên chỉ còn 9 lượt. `retry-after: 10` cũng khớp: 09:03:29 cộng 10 giây là lúc request đó hết hạn (09:03:39).
- **Admin:** `app.py:141` chọn limiter theo `role` trong JWT, nên admin dùng mức 100. Muốn bỏ hẳn giới hạn thì không gọi `limiter.check()` khi `role == "admin"`. Vì role nằm trong token đã ký, user không tự sửa được.
- **Hạn chế:** state nằm trong RAM, mỗi instance đếm riêng và restart là mất. Part 6 chuyển sang Redis.

### Exercise 4.4: Cost guard implementation

Code: `04-api-gateway/production/cost_guard_redis.py`.

- **Theo user và theo tháng:** key `budget:<user>:<YYYY-MM>` (giờ UTC), budget $10. Sang tháng mới là key mới nên tổng tự về 0. TTL 32 ngày để Redis tự dọn key cũ.
- **Kiểm tra và cộng trong một script Lua:** nếu `GET` rồi `INCRBYFLOAT` là hai lệnh riêng, hai request đồng thời có thể cùng thấy còn budget và cùng cộng, làm vượt mức. Redis chạy script nguyên khối nên không xảy ra.
- **State trong Redis:** mọi instance dùng chung một tổng, restart app không mất số liệu.

```console
$ python cost_guard_redis.py
1. $6   : True
2. $4   : True (vừa đủ $10)
3. $0.01: False (vượt $10)
4. user khác $6      : True
5. demo-user tháng 12: True
6. tổng tháng 11     : 10
7. TTL (ngày)        : 32
8. 50 request $1 song song, được duyệt: 10
```

Dòng 8: 50 request $1 chạy song song với budget $10, đúng 10 request được duyệt.

**Rate limit và cost guard khác nhau thế nào:** rate limit giới hạn tốc độ (số request mỗi phút), bảo vệ hệ thống khỏi bị gọi dồn. Cost guard giới hạn tổng tiền. Cần cả hai: gọi chậm đều 24 giờ vẫn đốt hết tiền dù không chạm rate limit, còn gọi dồn câu rẻ vẫn làm nghẽn dù chưa hết budget.

**Nhận xét về app mẫu:** trường `budget_remaining_usd` (`app.py:160`) trả về `usage.total_cost_usd`, tức số tiền đã tiêu chứ không phải còn lại. Vì vậy output 4.2 hiện `2.1e-05`.

## Part 5: Scaling & Reliability

### Exercise 5.1-5.5: Implementation notes

**5.1 Health checks** (`05-scaling-reliability/develop/app.py`)

| | `/health` (dòng 105) | `/ready` (dòng 148) |
|---|---|---|
| Trả lời câu hỏi | Process còn sống không? (liveness) | Nhận traffic được chưa? (readiness) |
| Kiểm tra | Process phản hồi, kèm mức dùng RAM | Cờ `_is_ready`: 503 khi đang khởi động hoặc đang tắt |
| Platform làm gì khi fail | Restart container | Ngừng gửi traffic, không restart |

Không nên để `/health` phụ thuộc Redis: Redis chết thì mọi instance đều bị restart, trong khi restart không sửa được Redis. Đó là việc của `/ready`.

```console
$ curl -i http://localhost:8000/health
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 09:12:25 GMT
server: uvicorn
content-length: 185
content-type: application/json

{"status":"ok","uptime_seconds":8.7,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T09:12:25.669010+00:00","checks":{"memory":{"status":"ok","used_percent":12.9}}}

$ curl -i http://localhost:8000/ready
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 09:12:44 GMT
server: uvicorn
content-length: 37
content-type: application/json

{"ready":true,"in_flight_requests":1}
```

`in_flight_requests` là 1 vì middleware đếm cả chính request `/ready` đang chạy.

**5.2 Graceful shutdown**

Gửi một request rồi SIGTERM ngay khi nó đang được xử lý:

```console
$ curl -i -X POST "http://localhost:8000/ask?question=Long%20task" & sleep 0.05; pkill -TERM -f "python app.py"; wait
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 09:12:48 GMT
server: uvicorn
content-length: 126
content-type: application/json

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

```text
INFO:     Shutting down
INFO:     127.0.0.1:53032 - "POST /ask?question=Long%20task HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
2026-11-25 16:12:52,157 INFO 🔄 Graceful shutdown initiated...
2026-11-25 16:12:52,157 INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [3244]
2026-11-25 16:12:52,157 INFO Received signal 15 — uvicorn will handle graceful shutdown
```

`Shutting down` đứng trước dòng `POST ... 200`: uvicorn nhận SIGTERM, ngừng nhận kết nối mới, chờ request đang chạy xong rồi mới chạy phần shutdown của lifespan (đặt `_is_ready = False`, chờ `_in_flight_requests` về 0). Không request nào bị cắt ngang.

**5.3 Stateless design** (`05-scaling-reliability/production/app.py`)

- Lịch sử hội thoại lưu ở Redis với key `session:<id>`, TTL 3600 giây (`setex`, dòng 63), không nằm trong RAM của process. Instance nào cũng đọc được cùng session.
- Nếu để trong RAM: request 1 vào instance A, request 2 vào instance B thì B không thấy lịch sử, và restart là mất.
- **Hạn chế của bài mẫu:** khi Redis không kết nối được lúc khởi động, app chuyển sang `_memory_store` (dòng 43–44) và `/ready` vẫn trả 200, tức là âm thầm trở lại stateful. Part 6 cần trả 503 ở `/ready`. Ngoài ra `append_to_history` đọc rồi ghi lại cả session nên hai request song song cùng session có thể mất tin nhắn. Dùng `RPUSH` sẽ tránh được.

**5.4 Load balancing**

```console
$ docker compose -p k5-day14-scaling up -d --build --scale agent=3
$ docker compose -p k5-day14-scaling ps
NAME                       IMAGE                    SERVICE   STATUS                    PORTS
k5-day14-scaling-agent-1   k5-day14-scaling-agent   agent     Up 25 seconds (healthy)   8000/tcp
k5-day14-scaling-agent-2   k5-day14-scaling-agent   agent     Up 26 seconds (healthy)   8000/tcp
k5-day14-scaling-agent-3   k5-day14-scaling-agent   agent     Up 25 seconds (healthy)   8000/tcp
k5-day14-scaling-nginx-1   nginx:alpine             nginx     Up 25 seconds             0.0.0.0:8080->80/tcp, [::]:8080->80/tcp
k5-day14-scaling-redis-1   redis:7-alpine           redis     Up 36 seconds (healthy)   6379/tcp
```

Trường `served_by` trong output bài 5.5 cho thấy 5 request `POST /chat` được chia cho cả 3 instance:

| Agent | Instance | Số `POST /chat` |
|---|---|---:|
| agent-1 | instance-91947a | 1 |
| agent-2 | instance-0b4e50 | 2 |
| agent-3 | instance-562af6 | 2 |

**5.5 Test stateless**

```console
$ python test_stateless.py
============================================================
Stateless Scaling Demo
============================================================

Session ID: f5044c7d-4cae-4c76-a6e3-78fdfd17396c

Request 1: [instance-562af6]
  Q: What is Docker?
  A: Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!...

Request 2: [instance-0b4e50]
  Q: Why do we need containers?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

Request 3: [instance-91947a]
  Q: What is Kubernetes?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 4: [instance-562af6]
  Q: How does load balancing work?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 5: [instance-0b4e50]
  Q: What is Redis used for?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

------------------------------------------------------------
Total requests: 5
Instances used: {'instance-91947a', 'instance-562af6', 'instance-0b4e50'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
  [user]: What is Docker?...
  [assistant]: Container là cách đóng gói app để chạy ở mọi nơi. Build once...
  [user]: Why do we need containers?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...
  [user]: What is Kubernetes?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...
  [user]: How does load balancing work?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...
  [user]: What is Redis used for?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...

✅ Session history preserved across all instances via Redis!
```

Script gửi 5 câu trong cùng session rồi đọc lại history. Script không tự tắt instance nào. Ở một lần chạy riêng trước đó (session `b393c903-...`, cũng 5 câu hỏi), tôi tắt một agent rồi đọc lại history:

```console
$ docker stop k5-day14-scaling-agent-1        # thoát với exit code 0
$ SID=b393c903-d276-4079-82b4-a4bafb64dd75
$ for i in 1 2 3 4 5 6; do curl -s -o /dev/null -w "req $i: %{http_code} %{time_total}s by %header{x-served-by}\n" http://localhost:8080/chat/$SID/history; done
req 1: 200 0.002400s by 172.19.0.3:8000
req 2: 200 0.002303s by 172.19.0.5:8000
req 3: 200 0.002211s by 172.19.0.3:8000
req 4: 200 0.002190s by 172.19.0.5:8000
req 5: 200 3.082579s by 172.19.0.4:8000, 172.19.0.3:8000
req 6: 200 0.006384s by 172.19.0.5:8000

$ curl -s http://localhost:8080/chat/$SID/history | python -c "import sys,json; print('count =', json.load(sys.stdin)['count'])"
count = 10
```

- Mất một instance, history vẫn đủ 10 tin (5 câu hỏi, 5 câu trả lời) vì state nằm trong Redis.
- Cả 6 request đều 200. Request 5 mất 3.08 giây: Nginx thử `172.19.0.4` (instance đã tắt) trước, thất bại rồi chuyển sang `172.19.0.3` nhờ `proxy_next_upstream`. Người dùng không thấy lỗi nhưng bị chậm, nên production cần `proxy_connect_timeout` ngắn và cập nhật danh sách upstream khi instance rời đi.

## AI log

| Phần | Tôi hỏi gì | AI gợi ý gì | Tôi tự sửa và kiểm tra thế nào |
|---|---|---|---|
| Setup (CP0) | Vì sao Docker không chạy trong Ubuntu, nên dùng Python nào | Claude Code chẩn đoán, khởi động lại WSL và Docker Desktop, đề xuất Python 3.11 bằng `uv` vì `pydantic-core` 2.23.2 không có bản cài sẵn cho 3.14 | WSL và Docker Desktop hoạt động lại bình thường; thống nhất sử dụng Python 3.11 qua uv để đảm bảo tương thích với pydantic-core 2.23.2|
| Part 1 | Cách chạy Part 1, vì sao bản production không in log JSON | Claude Code đưa lệnh, chạy thử ở cổng 8011 để tìm nguyên nhân, và soạn nháp các bảng 1.1, 1.3 cùng phần nhận xét | Tôi tự chạy các lệnh curl và `pkill` ở trên, output là của tôi. Đã tự chạy lệnh kiểm tra API và quản lý tiến trình; xác nhận, thu thập output thực tế để đối chiếu kết quả Part 1. |
| Part 2 | Vì sao `docker build` báo 429, cách chạy các bài 2.2–2.4 | Claude Code xác định hết lượt tải của Docker Hub theo IP, đề xuất mirror `mirror.gcr.io`, tính phần trăm chênh lệch, lấy output `docker compose ps`, soạn nháp câu trả lời 2.1, 2.3 và sơ đồ 2.4 | Tôi tự cấu hình mirror, build hai image, chạy container, bật stack và chạy các lệnh curl. (điền thêm) |
| Part 4 | Cách chạy 4.1–4.3, cách làm cost guard bằng Redis | Claude Code đưa lệnh, viết `cost_guard_redis.py` (script Lua) và chạy thử với Redis tạm, giải thích vì sao 429 ở request 10, soạn nháp câu trả lời | Tôi tự chạy các lệnh curl, vòng lặp 429 và `python cost_guard_redis.py`, output là của tôi. (điền thêm) |
| Part 5 | Vì sao cổng 8000 bị chiếm, vì sao curl treo khi tắt một instance, cách làm 5.1–5.5 | Claude Code chỉ ra server bị Ctrl+Z, biến `SID` rỗng, lấy log chia tải, đo thử failover và soạn nháp phần giải thích | Tôi tự chạy server, gửi SIGTERM, bật stack 3 agent, tắt agent-1 và đo lại 6 request, output là của tôi. (điền thêm) |
