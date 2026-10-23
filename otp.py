# -*- coding: utf-8 -*-
"""Gmail IMAP üzerinden VFS OTP (tek seferlik kod) okuma modülü.

Senkron imaplib kullanır; monitor.py içinde asyncio.to_thread ile çağrılmalıdır.
"""

from __future__ import annotations

import email
import imaplib
import logging
import re
import time
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Optional

logger = logging.getLogger("vfs-otp")


def decode_mime_header(value: str) -> str:
    if not value:
        return ""
    decoded_parts = decode_header(value)
    result = []
    for part, enc in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="ignore"))
        else:
            result.append(part)
    return "".join(result)


def extract_email_body(msg) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            disposition = str(part.get("Content-Disposition") or "")
            if "attachment" in disposition.lower():
                continue
            content_type = part.get_content_type()
            if content_type in ("text/plain", "text/html"):
                payload = part.get_payload(decode=True)
                if payload:
                    body += payload.decode(errors="ignore") + "\n"
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode(errors="ignore")
    return body


def get_vfs_otp_sync(
    email_user: str,
    email_pass: str,
    since_timestamp: Optional[float] = None,
    imap_host: str = "imap.gmail.com",
) -> Optional[str]:
    """Gmail IMAP üzerinden son VFS OTP kodunu döndürür.

    Args:
        email_user: Gmail adresi (Uygulama Şifresi gerektirir, 2FA açık olmalı).
        email_pass: Gmail Uygulama Şifresi (App Password).
        since_timestamp: Bu zaman damgasından sonra gelen mailler aranır.
        imap_host: IMAP sunucusu (varsayılan imap.gmail.com).

    Returns:
        6 haneli OTP kodu ya da None.
    """
    mail = None
    try:
        logger.info(f"IMAP bağlantısı kuruluyor: {imap_host}")
        mail = imaplib.IMAP4_SSL(imap_host)
        mail.login(email_user, email_pass)
        mail.select("INBOX")

        status, data = mail.search(None, "(UNSEEN)")
        ids = data[0].split() if status == "OK" and data and data[0] else []

        if not ids:
            status, data = mail.search(None, "ALL")
            ids = data[0].split()[-30:] if status == "OK" and data and data[0] else []

        if not ids:
            logger.warning("Inbox içinde aday mail yok.")
            return None

        candidate_ids = ids[-30:]
        otp_pattern = re.compile(r"\b(\d{6})\b")

        for msg_id in reversed(candidate_ids):
            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue

            for part in msg_data:
                if not isinstance(part, tuple):
                    continue

                msg = email.message_from_bytes(part[1])

                # Zaman filtresi
                if since_timestamp is not None:
                    date_str = msg.get("Date", "")
                    try:
                        email_dt = parsedate_to_datetime(date_str)
                        email_ts = email_dt.timestamp()
                        if email_ts < since_timestamp - 30:
                            continue
                    except Exception:
                        pass

                msg_from = decode_mime_header(msg.get("From", "")).lower()
                subject = decode_mime_header(msg.get("Subject", "")).lower()
                body = extract_email_body(msg).lower()

                looks_relevant = any(
                    x in (msg_from + " " + subject + " " + body)
                    for x in ["vfs", "vfsglobal", "otp", "verification", "one time password"]
                )
                if not looks_relevant:
                    continue

                match = otp_pattern.search(body)
                if match:
                    otp = match.group(1)
                    logger.info(f"OTP bulundu: {otp}")
                    return otp

    except Exception as exc:  # noqa: BLE001
        logger.error(f"IMAP Hatası: {exc}")
    finally:
        if mail is not None:
            try:
                mail.close()
            except Exception:
                pass
            try:
                mail.logout()
            except Exception:
                pass

    return None
