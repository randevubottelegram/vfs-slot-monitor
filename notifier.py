# -*- coding: utf-8 -*-
"""Telegram bildirim modülü.

İki modda çalışır:
  1. python-telegram-bot kütüphanesi (yüksek seviyeli, komutlar için)
  2. Doğrudan Telegram Bot API HTTP istekleri (basit mesaj gönderimi)
"""

from __future__ import annotations

import os
from typing import Optional

import requests


class TelegramNotifier:
    """Telegram'a mesaj göndermek için minimal sarmalayıcı."""

    def __init__(self, token: str, chat_id: Optional[str] = None) -> None:
        self.token = token.strip()
        self.chat_id = (chat_id or "").strip()
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def _headers(self) -> dict:
        return {"Content-Type": "application/json"}

    def send_message(self, text: str, chat_id: Optional[str] = None, parse_mode: str = "Markdown") -> bool:
        """Tek bir mesaj gönderir. Başarılıysa True döndürür."""
        target_chat = chat_id or self.chat_id
        if not self.token or not target_chat:
            print("[Telegram] Token veya chat_id eksik, mesaj atılmadı.")
            return False

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=20)
            if resp.status_code == 200:
                return True
            print(f"[Telegram] Hata {resp.status_code}: {resp.text[:200]}")
        except Exception as exc:  # noqa: BLE001
            print(f"[Telegram] İstek hatası: {exc}")
        return False

    def send_slot_alert(
        self,
        country_name: str,
        flag: str,
        status: str,
        detail: str,
        url: str,
        chat_id: Optional[str] = None,
    ) -> bool:
        """Randevu slot durumu değişikliği için formatlanmış uyarı."""
        emoji = {"OPEN": "✅", "WAITLIST": "⏳", "CLOSED": "❌", "ERROR": "⚠️", "UNKNOWN": "🟡"}.get(status.upper(), "🟡")
        text = (
            f"{emoji} *VFS Randevu Slot Uyarısı*\n\n"
            f"{flag} *Ülke:* {country_name}\n"
            f"🚦 *Durum:* {status.upper()}\n"
            f"📝 *Açıklama:* {detail}\n"
            f"🔗 *Link:* {url}\n\n"
            f"Bot çalışmaya devam ediyor..."
        )
        return self.send_message(text, chat_id=chat_id)

    def send_startup(self, country_name: str, flag: str, interval: int, chat_id: Optional[str] = None) -> bool:
        text = (
            f"🤖 *VFS Slot Takip Botu Başlatıldı*\n\n"
            f"{flag} *Ülke:* {country_name}\n"
            f"⏱️ *Kontrol aralığı:* {interval} saniye\n"
            f"Slot açıldığında size buradan bildirim gönderirim."
        )
        return self.send_message(text, chat_id=chat_id)

    def send_status(self, country_name: str, flag: str, status: str, detail: str, chat_id: Optional[str] = None) -> bool:
        emoji = {"OPEN": "✅", "CLOSED": "❌", "ERROR": "⚠️", "UNKNOWN": "🟡"}.get(status.upper(), "🟡")
        text = (
            f"{emoji} *Güncel Durum*\n\n"
            f"{flag} *Ülke:* {country_name}\n"
            f"🚦 *Durum:* {status.upper()}\n"
            f"📝 {detail}"
        )
        return self.send_message(text, chat_id=chat_id)
