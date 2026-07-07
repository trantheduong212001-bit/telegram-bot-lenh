# Telegram bot lệnh (GitHub Actions polling)

Bot Telegram trả lời lệnh, chạy hoàn toàn trên GitHub Actions — không cần server.
Cứ ~5 phút một lượt poll kéo dài ~4 phút (long-poll), nên phần lớn thời gian
lệnh được trả lời trong vài giây; chậm nhất ~5–15 phút.

## Hai bot, hai chuyên môn

| Bot | Lệnh | Kết quả |
|---|---|---|
| Bot chứng khoán (`BOT_TOKEN`) | `/gia` | Giá cổ phiếu mặc định (secret `DEFAULT_TICKERS`) |
| | `/gia HPG VNM` | Giá các mã chỉ định (API công khai VPS) |
| Bot báo cáo (`BAOCAO_BOT_TOKEN`) | `/baocao` | Báo cáo email 12 tiếng gần nhất (IMAP, chỉ đọc) |
| | `/baocao 24` | Báo cáo email 24 tiếng gần nhất |

Nhắn nhầm bot sẽ được chỉ sang bot đúng. `/help` ở cả hai bot.

## Secrets cần cấu hình

- `BOT_TOKEN` — token bot chứng khoán
- `BAOCAO_BOT_TOKEN` — token bot báo cáo email
- `CHAT_ID` — chỉ chat ID này được trả lời, người lạ bị bỏ qua
- `GMAIL_ACCOUNTS` — mỗi dòng `email:matkhauungdung` (mật khẩu ứng dụng Gmail, IMAP chỉ đọc)
- `DEFAULT_TICKERS` — mã mặc định cho `/gia`, phân cách bằng dấu phẩy

## Ghi chú

- Repo để công khai để được phút Actions không giới hạn; mọi thông tin nhạy cảm
  nằm trong Secrets, log không in nội dung tin nhắn/email.
- `offset.json` được commit lại sau mỗi lượt để không trả lời trùng.
- Workflow tự commit `heartbeat.txt` nếu repo im lặng 40 ngày (GitHub tắt cron
  của repo không hoạt động 60 ngày).
