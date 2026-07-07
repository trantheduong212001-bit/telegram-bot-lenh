# -*- coding: utf-8 -*-
"""
Module quét email + dựng báo cáo (dùng chung cho bot lệnh).
Quét các hộp Gmail qua IMAP (chỉ đọc), lọc nhiễu, phân loại, trả về văn bản tiếng Việt.
Không chứa bất kỳ thông tin cá nhân nào — tài khoản đọc từ biến môi trường GMAIL_ACCOUNTS.
"""
import email
import email.header
import email.utils
import html
import imaplib
import os
import re
import sys
from datetime import datetime, timezone, timedelta

VN_TZ = timezone(timedelta(hours=7))

TU_KHOA_QUAN_TRONG = [
    "otp", "xác minh", "verify", "verification", "bảo mật", "security",
    "cảnh báo", "alert", "đăng nhập", "sign-in", "signin", "password", "mật khẩu",
    "ngân hàng", "bank", "vietcombank", "techcombank", "bidv", "vpbank", "mbbank",
    "thanh toán", "payment", "hóa đơn", "invoice", "biên lai", "receipt",
    "đơn hàng", "order", "giao hàng", "delivery", "chuyển khoản",
    "hợp đồng", "contract", "phỏng vấn", "interview", "tuyển dụng",
    "google ads", "api", "anthropic", "suspended", "khóa tài khoản", "hết hạn", "expire",
]

MAU_NHIEU = [
    "unsubscribe", "newsletter", "khuyến mãi", "ưu đãi", "giảm giá", "promotion",
    "sale off", "flash sale", "no-reply@youtube", "noreply@youtube",
    "facebookmail", "notification@tiktok", "shopee", "lazada", "tiki.vn",
    "quora", "pinterest", "medium.com", "linkedin.com", "digest",
]


def giai_ma_header(raw):
    if not raw:
        return ""
    parts = email.header.decode_header(raw)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            out.append(text.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(text)
    return " ".join(out).strip()


def phan_loai(sender, subject):
    s = f"{sender} {subject}".lower()
    for m in MAU_NHIEU:
        if m in s:
            return "nhieu"
    for k in TU_KHOA_QUAN_TRONG:
        if k in s:
            return "quantrong"
    return "thuong"


def quet_hop_thu(addr, app_password, cutoff_utc):
    mails = []
    imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        imap.login(addr, app_password)
        imap.select("INBOX", readonly=True)
        since = cutoff_utc.strftime("%d-%b-%Y")
        _, data = imap.search(None, f"(SINCE {since})")
        ids = data[0].split()
        for mid in ids[-200:]:
            _, msg_data = imap.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            try:
                dt = email.utils.parsedate_to_datetime(msg.get("Date"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if dt < cutoff_utc:
                continue
            sender = giai_ma_header(msg.get("From"))
            sender = re.sub(r"\s*<[^>]+>", "", sender).strip().strip('"') or sender
            subject = giai_ma_header(msg.get("Subject")) or "(không tiêu đề)"
            mails.append((sender, subject, dt))
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    return mails


def cat(s, n):
    s = s if len(s) <= n else s[: n - 1] + "…"
    return html.escape(s)


def doc_tai_khoan():
    accounts = []
    for line in os.environ.get("GMAIL_ACCOUNTS", "").splitlines():
        line = line.strip()
        if line and ":" in line and not line.startswith("#"):
            addr, pw = line.split(":", 1)
            accounts.append((addr.strip(), pw.strip()))
    return accounts


def tao_bao_cao(hours):
    """Quét tất cả tài khoản trong GMAIL_ACCOUNTS, trả về văn bản báo cáo (HTML Telegram)."""
    accounts = doc_tai_khoan()
    if not accounts:
        return "Thiếu cấu hình GMAIL_ACCOUNTS."
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    now_vn = datetime.now(VN_TZ)
    lines = [f"📧 Báo cáo email {int(hours)} tiếng qua ({now_vn:%H:%M %d/%m}, bot mây ☁️):"]

    for addr, pw in accounts:
        ten = addr.split("@")[0]
        try:
            mails = quet_hop_thu(addr, pw, cutoff)
        except Exception as e:
            lines.append(f"\n📪 <b>{ten}</b>: LỖI đọc hộp thư ({cat(str(e), 60)})")
            continue

        quantrong = [(s, sub) for s, sub, _ in mails if phan_loai(s, sub) == "quantrong"]
        thuong = [(s, sub) for s, sub, _ in mails if phan_loai(s, sub) == "thuong"]
        nhieu_count = len(mails) - len(quantrong) - len(thuong)

        if not mails:
            lines.append(f"\n📪 <b>{ten}</b>: không có mail mới")
            continue

        lines.append(f"\n📬 <b>{ten}</b>: {len(mails)} mail mới")
        if quantrong:
            lines.append("⚠️ <b>Cần để mắt:</b>")
            for s, sub in quantrong[:8]:
                lines.append(f"  • {cat(s, 25)}: {cat(sub, 60)}")
        if thuong:
            lines.append(f"Khác ({len(thuong)}):")
            for s, sub in thuong[:5]:
                lines.append(f"  • {cat(s, 25)}: {cat(sub, 55)}")
            if len(thuong) > 5:
                lines.append(f"  … và {len(thuong) - 5} mail nữa")
        if nhieu_count:
            lines.append(f"🔕 Bỏ qua {nhieu_count} mail quảng cáo/thông báo mạng xã hội")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3990] + "\n(…cắt bớt)"
    return text
