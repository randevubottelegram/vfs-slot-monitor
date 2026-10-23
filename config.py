# -*- coding: utf-8 -*-
"""Yapılandırma: ülke listesi, ortam değişkenleri ve yardımcı fonksiyonlar."""

from __future__ import annotations

import imaplib
import email
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# .env dosyasını yükle (varsa)
load_dotenv(BASE_DIR / ".env")

# Ortam değişkenleri
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "").strip()
CHECK_INTERVAL_SECONDS: int = int(os.getenv("CHECK_INTERVAL_SECONDS", "300"))


def load_countries(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """countries.json dosyasından ülke listesini yükler."""
    p = path or (BASE_DIR / "countries.json")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def find_country(countries: List[Dict[str, Any]], key: str) -> Optional[Dict[str, Any]]:
    """key ile ülke bulur."""
    for c in countries:
        if c.get("key") == key:
            return c
    return None


def find_country_by_name(countries: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    """Türkçe veya İngilizce isimle ülke bulur (büyük/küçük harfe duyarlı değil)."""
    name_lower = name.strip().lower()
    for c in countries:
        if c.get("name", "").lower() == name_lower or c.get("name_en", "").lower() == name_lower:
            return c
    return None


def country_credentials_key(country_key: str, field: str) -> str:
    """Ülkeye özgü kimlik bilgi ortam değişkeni adını döndürür.
    Örn: VFS_FR_EMAIL -> VFS_{KEY_UPPER}_EMAIL
    """
    prefix = f"VFS_{country_key.upper()}"
    return f"{prefix}_{field.upper()}"


def get_credentials(country: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Ülke için .env'de tanımlanmış VFS kimlik bilgilerini döndürür."""
    ck = country.get("key", "").upper()
    return {
        "email": os.getenv(f"VFS_{ck}_EMAIL"),
        "password": os.getenv(f"VFS_{ck}_PASSWORD"),
        "imap_app_password": os.getenv(f"VFS_{ck}_IMAP_APP_PASSWORD"),
    }
