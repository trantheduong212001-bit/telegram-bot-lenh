# -*- coding: utf-8 -*-
"""
Bot lệnh Telegram chạy trên GitHub Actions (polling) — nghe 2 bot, mỗi bot một chuyên môn:

  • Bot CHỨNG KHOÁN (BOT_TOKEN):        /gia [MÃ...] — giá cổ phiếu
  • Bot BÁO CÁO EMAIL (BAOCAO_BOT_TOKEN): /baocao [giờ] — báo cáo email

Nhắn nhầm chuyên môn sẽ được chỉ sang bot đúng. Lệnh gõ có / hay không đều được.

Mỗi lượt chạy kéo dài ~4 phút, long-poll luân phiên 2 bot nên lệnh gửi trong
lúc bot đang chạy được trả lời trong vài giây; ngoài khung đó chờ lượt cron
kế tiếp (tối đa ~5–15 phút).

Bảo mật: chỉ trả lời đúng CHAT_ID trong secrets; tin nhắn từ người lạ bị bỏ qua.
Không in nội dung tin nhắn hay email ra log (log của kho công khai ai cũng xem được).
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

import bao_cao_email as bce

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
OFFSET_FILE = BASE / "offset.json"
VN_TZ = timezone(timedelta(hours=7))
PRICE_API = "https://bgapidatafeed.vps.com.vn/getliststockdata/{tickers}"
RUN_SECONDS = 240          # mỗi lượt Actions poll ~4 phút
BO_QUA_TIN_CU_GIO = 6      # lệnh cũ hơn 6 tiếng thì bỏ qua, không trả lời lại


def tg(token, method, **params):
    data = urllib.parse.urlencode(params).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/{method}"
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def reply(token, chat_id, text):
    tg(token, "sendMessage", chat_id=chat_id, text=text,
       parse_mode="HTML", disable_web_page_preview="true")


def fmt_price(x):
    return f"{x:,.2f}".rstrip("0").rstrip(".")


def lenh_gia(tickers):
    url = PRICE_API.format(tickers=",".join(t.upper() for t in tickers))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        rows = json.loads(r.read().decode("utf-8"))
    now_vn = datetime.now(VN_TZ)
    lines = [f"📊 Giá lúc {now_vn:%H:%M %d/%m}:"]
    found = set()
    for row in rows:
        sym = (row.get("sym") or "").upper()
        if not sym:
            continue
        found.add(sym)
        last = row.get("lastPrice") or 0
        lines.append(
            f"• <b>{sym}</b>: {fmt_price(last)} ({row.get('changePc', '?')}%) — "
            f"cao {row.get('highPrice', '?')} / thấp {row.get('lowPrice', '?')} / TC {row.get('r', '?')}"
        )
    for t in tickers:
        if t.upper() not in found:
            lines.append(f"• {t.upper()}: không lấy được dữ liệu")
    lines.append("<i>(đơn vị: nghìn đồng/cp)</i>")
    return "\n".join(lines)


def la_lenh_gia(t):
    return t.startswith(("gia", "giá"))


def la_lenh_baocao(t):
    return t.startswith(("baocao", "bao cao", "báo cáo", "báocáo"))


def xu_ly_ssi(text, default_tickers):
    """Bot chứng khoán: chỉ lo giá cả."""
    t = text.strip().lower().lstrip("/")
    if la_lenh_gia(t):
        parts = [p for p in text.split()[1:] if p.strip()]
        tickers = parts or default_tickers
        if not tickers:
            return "Chưa cấu hình mã mặc định. Dùng: /gia SHB"
        return lenh_gia(tickers)
    if la_lenh_baocao(t):
        return "📧 Báo cáo email anh nhắn bên bot @BaocaoDuongbot nhé."
    return ("🤖 Bot chứng khoán — lệnh hỗ trợ:\n"
            "• /gia — giá cổ phiếu đang canh\n"
            "• /gia HPG VNM — giá mã bất kỳ\n"
            "(Báo cáo email: nhắn bot @BaocaoDuongbot)")


def xu_ly_baocao(text):
    """Bot báo cáo: chỉ lo email."""
    t = text.strip().lower().lstrip("/")
    if la_lenh_baocao(t):
        hours = 12
        for p in text.split()[1:]:
            try:
                hours = max(1, min(72, float(p)))
                break
            except ValueError:
                pass
        return bce.tao_bao_cao(hours)
    if la_lenh_gia(t):
        return "📊 Giá cổ phiếu anh hỏi bên bot @SSIChungKhoanBot nhé."
    return ("🤖 Bot báo cáo email — lệnh hỗ trợ:\n"
            "• /baocao — báo cáo email 12 tiếng qua\n"
            "• /baocao 24 — báo cáo email 24 tiếng qua\n"
            "(Giá cổ phiếu: nhắn bot @SSIChungKhoanBot)")


def main():
    chat_id = os.environ["CHAT_ID"]
    default_tickers = [t for t in os.environ.get("DEFAULT_TICKERS", "").split(",") if t.strip()]

    bots = {
        "ssi": {
            "token": os.environ["BOT_TOKEN"],
            "handler": lambda text: xu_ly_ssi(text, default_tickers),
        },
        "baocao": {
            "token": os.environ["BAOCAO_BOT_TOKEN"],
            "handler": xu_ly_baocao,
        },
    }

    try:
        offsets = json.loads(OFFSET_FILE.read_text(encoding="utf-8"))
    except Exception:
        offsets = {}
    for key in bots:
        offsets.setdefault(key, 0)

    start = time.time()
    handled = 0
    while time.time() - start < RUN_SECONDS:
        for key, bot in bots.items():
            try:
                resp = tg(bot["token"], "getUpdates", offset=offsets[key] + 1, timeout=8)
            except Exception:
                time.sleep(3)
                continue
            for u in resp.get("result", []):
                offsets[key] = max(offsets[key], u["update_id"])
                OFFSET_FILE.write_text(json.dumps(offsets), encoding="utf-8")
                msg = u.get("message") or u.get("edited_message") or {}
                if str(msg.get("chat", {}).get("id", "")) != str(chat_id):
                    continue  # người lạ — bỏ qua im lặng
                if time.time() - msg.get("date", 0) > BO_QUA_TIN_CU_GIO * 3600:
                    continue  # lệnh quá cũ
                text = (msg.get("text") or "").strip()
                if not text:
                    continue
                try:
                    answer = bot["handler"](text)
                except Exception as e:
                    answer = f"⚠️ Lỗi xử lý lệnh: {type(e).__name__}"
                try:
                    reply(bot["token"], chat_id, answer)
                    handled += 1
                except Exception as e:
                    print(f"Lỗi gửi trả lời ({key}): {type(e).__name__}")

    print(f"Hết lượt poll. Đã trả lời {handled} lệnh. Offsets: {offsets}")


if __name__ == "__main__":
    main()
