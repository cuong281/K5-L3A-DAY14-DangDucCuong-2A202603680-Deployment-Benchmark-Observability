# Deployment Information

## Public URL

https://day14-agent-rbpr.onrender.com

## Platform

Render, deploy agent Part 6 (`06-lab-complete/`) bằng Blueprint `06-lab-complete/render.yaml`:

- `day14-agent`: Web Service, build từ `06-lab-complete/Dockerfile`, gói Free, region Singapore.
- `day14-redis`: Key Value (tương thích Redis), gói Free, chỉ cho kết nối nội bộ.

Service gói Free tự ngủ khi không có truy cập, nên request đầu tiên sau đó có thể chậm. Redis gói Free không lưu dữ liệu qua lần restart.

## Test Commands

`AGENT_API_KEY` là key đặt trên Render, không ghi trong repo.

```bash
BASE=https://day14-agent-rbpr.onrender.com
read -rs -p "AGENT_API_KEY: " AGENT_API_KEY; echo
```

### Health check, readiness và xác thực

```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```

Kết quả chạy ngày 25/11/2026: `200`, `200`, `401`, `200`.

### Rate limit (10 request/phút)

```bash
for i in {1..12}; do curl -sS -o /dev/null -w '%{http_code} ' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'; done; echo
```

Kết quả lúc 22:30 ngày 25/11/2026: `200 200 200 200 200 200 200 200 200 429 429 429`. Request có key ngay trước vòng lặp đã dùng 1 lượt, nên đúng 10 request được chấp nhận rồi mới 429.

`screenshots/test.png` là output của script chạy các lệnh trên, được kết xuất thành ảnh.

## Environment Variables Set

| Biến | Cách đặt |
|---|---|
| `PORT` | Render cấp |
| `REDIS_URL` | Lấy từ `day14-redis` (`fromService`) |
| `AGENT_API_KEY` | Render tự sinh (`generateValue`), không nằm trong Git |
| `ENVIRONMENT` | `production` |
| `LOG_LEVEL` | `INFO` |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` | `1.0` |
| `MONTHLY_BUDGET_USD` | `10.0` |

## Screenshots

- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
