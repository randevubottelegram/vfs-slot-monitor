# -*- coding: utf-8 -*-
"""VFS Global randevu slot kontrol modülü (Camoufox anti-detect).

Camoufox ile VFS randevu sayfası açılır. İki mod desteklenir:

1. Girişsiz mod: Sadece sayfa metninden slot durumu tahmin edilir.
   (Çoğu VFS ülkesinde giriş yapmadan slot takvimi görünmez, bu yüzden
    genellikle LOGIN_FORM döner.)

2. Girişli mod: .env'de tanımlı VFS e-posta/şifre ve Gmail Uygulama Şifresi
   (IMAP) ile giriş yapılır, OTP IMAP'tan otomatik alınır ve dashboard'da
   gerçek slot durumu kontrol edilir.

Sonuç Telegram notifier ile bildirilir. Durum dosyasında (state.json)
son bilinen durum saklanır, böylece sadece durum değiştiğinde bildirim
gönderilir.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Page

from otp import get_vfs_otp_sync

logger = logging.getLogger("vfs-monitor")

# Varsayılan 'randevu yok' ipuçları (Türkçe/İngilizce karışık)
DEFAULT_CLOSED_TEXTS = [
    "no appointments available",
    "no available appointments",
    "randevu yok",
    "müsait randevu bulunamadı",
    "fully booked",
    "tüm randevular dolu",
    "appointment slots are currently unavailable",
    "no slots available",
    "randevu için müsait tarih yok",
]

# Varsayılan 'randevu var' ipuçları
DEFAULT_OPEN_TEXTS = [
    "select a date",
    "tarih seçin",
    "choose date",
    "available appointments",
    "randevu seç",
    "müsait randevu",
    "book appointment",
    "randevu al",
    "appointment calendar",
    "randevu takvimi",
    "müsait tarihler",
]

# Bekleme listesi açık ipuçları
DEFAULT_WAITLIST_TEXTS = [
    "waitlist",
    "bekleme listesi",
    "join waitlist",
    "bekleme listesine kaydol",
    "waiting list",
    "listeye kayıt olun",
    "add to waitlist",
    "bekleme listesine ekle",
    "waitlist open",
    "bekleme listesi açık",
]

# Oturum açıldıktan sonra karşılaşılacak 'randevu yok' / 'var' ipuçları
DASHBOARD_CLOSED_TEXTS = [
    "no available appointments",
    "no appointments available",
    "there are no available appointments",
    "no slots available",
    "randevu bulunamadı",
    "müsait randevu yok",
]
DASHBOARD_OPEN_TEXTS = [
    "select date",
    "tarih seç",
    "book now",
    "randevu oluştur",
    "available dates",
    "müsait tarihler",
    "appointment slots",
    "randevu slotları",
]
DASHBOARD_WAITLIST_TEXTS = [
    "waitlist",
    "bekleme listesi",
    "join waitlist",
    "bekleme listesine kaydol",
    "waiting list",
    "listeye kayıt olun",
    "add to waitlist",
    "bekleme listesine ekle",
]

# Giriş sayfasında kullanıcı/şifre alanlarını tespit etmek için
LOGIN_EMAIL_SELECTORS = [
    'input[formcontrolname="email"]',
    'input[name="email"]',
    'input[type="email"]',
    'input[placeholder*="email" i]',
]
LOGIN_PASSWORD_SELECTORS = [
    'input[formcontrolname="password"]',
    'input[name="password"]',
    'input[type="password"]',
    'input[placeholder*="şifre" i]',
    'input[placeholder*="password" i]',
]
LOGIN_SUBMIT_SELECTORS = [
    'button:has-text("Sign In")',
    'button:has-text("Sign in")',
    'button:has-text("Login")',
    'button:has-text("Giriş")',
    'button[type="submit"]',
]

# OTP giriş alanları
OTP_INPUT_SELECTORS = [
    'input[formcontrolname="otp"]',
    'input[name="otp"]',
    'input[placeholder*="otp" i]',
    'input[placeholder*="verification" i]',
    'input[placeholder*="doğrulama" i]',
    'input[type="text"][inputmode="numeric"]',
]
OTP_SUBMIT_SELECTORS = [
    'button:has-text("Verify")',
    'button:has-text("Doğrula")',
    'button:has-text("Submit")',
    'button:has-text("Gönder")',
    'button[type="submit"]',
]

# Cloudflare kuyruk (Waiting Room) ipuçları
CLOUDFLARE_QUEUE_TEXTS = [
    "estimated wait time",
    "virtual queue",
    "waiting room",
    "you are now in line",
    "high volume of traffic",
    "queue-it",
    "queueit",
    "this page will automatically refresh",
]

# Cloudflare güvenlik challenge (Just a moment) ipuçları
CLOUDFLARE_CHALLENGE_TEXTS = [
    "just a moment",
    "checking your browser",
    "cloudflare",
    "security check",
]

# Giriş yapıldığında dashboard'ta karşılaşılacak işaretler
DASHBOARD_INDICATORS = [
    "dashboard",
    "new booking",
    "yeni randevu",
    "randevu oluştur",
    "sign out",
    "çıkış yap",
    "appointments",
    "my appointments",
    "my profile",
    "profili",
]


class VFSMonitor:
    """Tek bir ülke için VFS slot durumu kontrolörü (Camoufox, girişli/girişsiz)."""

    def __init__(
        self,
        country: Dict[str, Any],
        state_dir: Path,
        headless: bool = True,
        credentials: Optional[Dict[str, Optional[str]]] = None,
    ) -> None:
        self.country = country
        self.key = country.get("key", "unknown")
        self.name = country.get("name", self.key)
        self.flag = country.get("flag", "")
        self.url = country.get("url", "")
        self.provider = country.get("provider", "VFS")
        self.headless = headless
        self.credentials = credentials or {}

        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / f"state_{self.key}.json"
        self.cookies_dir = self.state_dir / "cookies"
        self.cookies_dir.mkdir(parents=True, exist_ok=True)
        self.cookie_file = self.cookies_dir / f"cookies_{self.key}.json"

        self.closed_texts = list(DEFAULT_CLOSED_TEXTS) + list(
            country.get("closed_texts", [])
        )
        self.open_texts = list(DEFAULT_OPEN_TEXTS) + list(country.get("open_texts", []))

        self._camoufox = None
        self._browser = None

    # ------------------------------------------------------------------ #
    # State (kalıcı durum)
    # ------------------------------------------------------------------ #
    def _load_state(self) -> Dict[str, Any]:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_state(self, data: Dict[str, Any]) -> None:
        self.state_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------------ #
    # Cookie persistence (oturum kalıcılığı)
    # ------------------------------------------------------------------ #
    def _cookie_hash(self, email: str) -> str:
        return hashlib.md5(email.encode()).hexdigest()[:12]

    def _load_cookies(self, email: str) -> List[Dict[str, Any]]:
        """Kaydedilmiş çerezleri döndürür."""
        path = self.cookies_dir / f"vfs_{self._cookie_hash(email)}.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _save_cookies(self, email: str, cookies: List[Dict[str, Any]]) -> None:
        """Çerezleri kaydeder."""
        path = self.cookies_dir / f"vfs_{self._cookie_hash(email)}.json"
        try:
            path.write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            logger.warning(f"[{self.key}] Çerez kaydedilemedi: {exc}")

    # ------------------------------------------------------------------ #
    # Tarayıcı yaşam döngüsü (Camoufox)
    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        if self._camoufox is None:
            self._camoufox = await AsyncCamoufox(headless=self.headless).start()
            self._browser = self._camoufox
            logger.info(f"[{self.key}] Camoufox başlatıldı (headless={self.headless}).")

    async def stop(self) -> None:
        if self._camoufox:
            try:
                await self._camoufox.stop()
            except Exception:
                pass
            self._camoufox = None
            self._browser = None
            logger.info(f"[{self.key}] Camoufox durduruldu.")

    # ------------------------------------------------------------------ #
    # Tek seferlik kontrol
    # ------------------------------------------------------------------ #
    async def check_once(self) -> Dict[str, Any]:
        """Tek bir slot kontrolü yapar ve sonuç sözlüğü döndürür."""
        if self._browser is None:
            await self.start()

        assert self._browser is not None

        has_creds = bool(
            self.credentials.get("email") and self.credentials.get("password")
        )

        for attempt in range(5):
            page = await self._browser.new_page()
            try:
                logger.info(
                    f"[{self.key}] Sayfa açılıyor (deneme {attempt+1}/5): {self.url}"
                )
                await page.goto(self.url, wait_until="domcontentloaded", timeout=45000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=30000)
                except Exception:
                    pass
                await page.wait_for_timeout(8000)
                await self._dismiss_cookie_popups(page)

                body_text = ""
                try:
                    body_text = await page.locator("body").inner_text(timeout=10000)
                except Exception as exc:
                    logger.warning(f"[{self.key}] Body metni alınamadı: {exc}")

                body_lower = body_text.lower()

                # 1. Cloudflare güvenlik challenge
                if any(k in body_lower for k in CLOUDFLARE_CHALLENGE_TEXTS):
                    await page.close()
                    return {
                        "status": "CF_CHALLENGE",
                        "detail": "Cloudflare güvenlik challenge'ı aktif (Just a moment) — sayfaya erişilemiyor.",
                        "matched": "cloudflare_challenge",
                        "url": page.url,
                    }

                # 2. Cloudflare kuyruğu
                if any(k in body_lower for k in CLOUDFLARE_QUEUE_TEXTS):
                    await page.close()
                    import asyncio as _asyncio
                    await _asyncio.sleep(5 + attempt * 2)
                    continue

                # 3. Kimlik bilgisi varsa: önce oturumu geri yükle / giriş yap
                if has_creds:
                    email = self.credentials.get("email", "")
                    password = self.credentials.get("password", "")
                    imap_pass = self.credentials.get("imap_app_password", "")

                    # Çerez varsa dene
                    saved_cookies = self._load_cookies(email)
                    if saved_cookies:
                        try:
                            await page.context.add_cookies(saved_cookies)
                            logger.info(f"[{self.key}] Kayıtlı çerezler yüklendi: {email}")
                        except Exception as exc:
                            logger.debug(f"[{self.key}] Çerez yüklenemedi: {exc}")

                    # Dashboard'a gitmeye çalış (oturum var olabilir)
                    _dashboard_url = self.url.rsplit("/", 1)[0] + "/dashboard"
                    try:
                        await page.goto(_dashboard_url, wait_until="domcontentloaded", timeout=20000)
                        await page.wait_for_timeout(4000)
                        dash_body = (await page.locator("body").inner_text(timeout=8000)).lower()
                    except Exception:
                        dash_body = ""

                    if any(k in dash_body for k in DASHBOARD_INDICATORS):
                        logger.info(f"[{self.key}] Oturum geri yüklü, dashboard doğrulandı.")
                        await page.close()
                        return await self._check_dashboard_from_page(page)

                    # Yoksa giriş akışına git
                    await page.goto(self.url, wait_until="domcontentloaded", timeout=45000)
                    await page.wait_for_timeout(4000)
                    await self._dismiss_cookie_popups(page)

                    login_result = await self._attempt_login(page, email, password)
                    if login_result.get("needs_otp"):
                        if imap_pass:
                            otp = await asyncio.to_thread(
                                get_vfs_otp_sync, email, imap_pass
                            )
                            if otp:
                                otp_result = await self._submit_otp(page, otp)
                                if otp_result.get("logged_in"):
                                    await page.close()
                                    return await self._check_dashboard_from_page(page)
                                else:
                                    await page.close()
                                    return {
                                        "status": "ERROR",
                                        "detail": "OTP girildi ama giriş başarısız oldu.",
                                        "matched": "otp_failed",
                                        "url": page.url,
                                    }
                            else:
                                await page.close()
                                return {
                                    "status": "ERROR",
                                    "detail": "OTP ekranı çıktı ama IMAP'tan kod alınamadı.",
                                    "matched": "otp_not_found",
                                    "url": page.url,
                                }
                        else:
                            await page.close()
                            return {
                                "status": "NEEDS_OTP",
                                "detail": "Giriş yapıldı ama OTP (tek seferlik kod) gerekiyor. .env'de IMAP_APP_PASSWORD tanımlanmalı.",
                                "matched": "otp",
                                "url": page.url,
                            }

                    if login_result.get("logged_in"):
                        # Çerezleri kaydet
                        try:
                            cookies = await page.context.cookies()
                            self._save_cookies(email, cookies)
                        except Exception:
                            pass
                        await page.close()
                        return await self._check_dashboard_from_page(page)

                    # Giriş başarısız → sayfa metninden değerlendir
                    body_text = (await page.locator("body").inner_text(timeout=8000)).lower()
                    body_lower = body_text

                # 4. Bekleme listesi açık mı?
                for phrase in DEFAULT_WAITLIST_TEXTS:
                    if phrase.lower() in body_lower:
                        await page.close()
                        return {
                            "status": "WAITLIST",
                            "detail": f"Bekleme listesi açık: '{phrase}'.",
                            "matched": phrase,
                            "url": page.url,
                        }

                # 5. Randevu yok (kapalı)
                for phrase in self.closed_texts:
                    if phrase.lower() in body_lower:
                        await page.close()
                        return {
                            "status": "CLOSED",
                            "detail": f"Randevu yok: '{phrase}' ifadesi bulundu.",
                            "matched": phrase,
                            "url": page.url,
                        }

                # 6. Randevu var (açık)
                for phrase in self.open_texts:
                    if phrase.lower() in body_lower:
                        await page.close()
                        return {
                            "status": "OPEN",
                            "detail": f"Randevu formu/erişim bulundu: '{phrase}'.",
                            "matched": phrase,
                            "url": page.url,
                        }

                # 7. Form elemanı sayısına dayalı tahmin (fallback)
                try:
                    form_count = await page.locator("input, select, textarea, button").count()
                    if form_count >= 3:
                        if len(body_text.strip()) < 500:
                            await page.close()
                            return {
                                "status": "LOGIN_FORM",
                                "detail": "Yalnızca giriş formu mevcut (slot takvimi henüz görünmüyor).",
                                "matched": f"form_elemani:{form_count}",
                                "url": page.url,
                            }
                        await page.close()
                        return {
                            "status": "OPEN",
                            "detail": "İletişim/form elemanı bulundu (tahmini açık).",
                            "matched": f"form_elemani:{form_count}",
                            "url": page.url,
                        }
                except Exception:
                    pass

                await page.close()
                return {
                    "status": "UNKNOWN",
                    "detail": "Durum netleşemedi (sayfa metni eşleşmedi).",
                    "matched": "-",
                    "url": page.url,
                }

            except Exception as exc:  # noqa: BLE001
                logger.error(f"[{self.key}] Kontrol hatası (deneme {attempt+1}): {exc}")
                try:
                    await page.close()
                except Exception:
                    pass
                if attempt < 4:
                    import asyncio as _asyncio
                    await _asyncio.sleep(3 + attempt)
                continue

        return {
            "status": "ERROR",
            "detail": "Cloudflare kuyruğundan geçilemedi / sayfa erişilemiyor.",
            "matched": "-",
            "url": self.url,
        }

    # ------------------------------------------------------------------ #
    # Dashboard'dan slot kontrolü
    # ------------------------------------------------------------------ #
    async def _check_dashboard_from_page(self, page: Page) -> Dict[str, Any]:
        """Oturum açılmış sayfada randevu mevcutluğu arar."""
        body_text = ""
        try:
            body_text = await page.locator("body").inner_text(timeout=10000)
        except Exception as exc:
            logger.warning(f"[{self.key}] Dashboard metni alınamadı: {exc}")
        body_lower = body_text.lower()

        for phrase in DASHBOARD_WAITLIST_TEXTS:
            if phrase.lower() in body_lower:
                return {
                    "status": "WAITLIST",
                    "detail": f"Bekleme listesi açık (dashboard): '{phrase}'.",
                    "matched": phrase,
                    "url": page.url,
                }

        for phrase in DASHBOARD_CLOSED_TEXTS:
            if phrase.lower() in body_lower:
                return {
                    "status": "CLOSED",
                    "detail": f"Randevu yok (dashboard): '{phrase}'.",
                    "matched": phrase,
                    "url": page.url,
                }

        for phrase in DASHBOARD_OPEN_TEXTS:
            if phrase.lower() in body_lower:
                return {
                    "status": "OPEN",
                    "detail": f"Randevu mevcut (dashboard): '{phrase}'.",
                    "matched": phrase,
                    "url": page.url,
                }

        try:
            form_count = await page.locator("input, select, textarea, button").count()
            if form_count >= 5:
                return {
                    "status": "OPEN",
                    "detail": "Dashboard'da çok sayıda form elemanı var (tahmini açık).",
                    "matched": f"form_elemani:{form_count}",
                    "url": page.url,
                }
        except Exception:
            pass

        return {
            "status": "UNKNOWN",
            "detail": "Dashboard durumu netleşemedi.",
            "matched": "-",
            "url": page.url,
        }

    # ------------------------------------------------------------------ #
    # Giriş akışı
    # ------------------------------------------------------------------ #
    async def _attempt_login(
        self, page: Page, email: str, password: str
    ) -> Dict[str, Any]:
        """E-posta/şifre doldurup giriş yapar. Best-effort."""
        result: Dict[str, Any] = {"logged_in": False, "needs_otp": False}

        email_selector = await self._first_visible(page, LOGIN_EMAIL_SELECTORS, timeout_ms=8000)
        if not email_selector:
            logger.debug(f"[{self.key}] Giriş formu bulunamadı.")
            return result

        await self._fill_visible(page, LOGIN_EMAIL_SELECTORS, email)
        await self._fill_visible(page, LOGIN_PASSWORD_SELECTORS, password)
        await self._dismiss_cookie_popups(page)
        await self._wait_cloudflare(page)

        submitted = await self._click_visible(page, LOGIN_SUBMIT_SELECTORS)
        if not submitted:
            try:
                js_result = await page.evaluate(
                    """
                    (function(){
                      var bs = document.querySelectorAll('button[type="submit"], button');
                      for (var b of bs){
                        var t = (b.textContent||'').toLowerCase();
                        if (t.includes('sign in') || t.includes('login') || t.includes('giriş') || b.type==='submit'){
                          b.removeAttribute('disabled'); b.click(); return b.textContent.trim();
                        }
                      }
                      return null;
                    })()
                    """
                )
                submitted = bool(js_result)
            except Exception:
                pass

        if not submitted:
            logger.warning(f"[{self.key}] Giriş butonu tıklanamadı.")
            return result

        await page.wait_for_timeout(5000)

        body_text = (await page.locator("body").inner_text(timeout=10000)).lower()
        current_url = page.url

        # OTP ekranı tespiti
        if any(k in body_text for k in ["otp", "verification code", "doğrulama kodu", "one-time password"]):
            result["needs_otp"] = True
            return result

        # Başarılı giriş işaretleri
        if any(k in body_text for k in DASHBOARD_INDICATORS) or (
            "login" not in current_url.lower() and "sign-in" not in current_url.lower()
        ):
            result["logged_in"] = True

        return result

    async def _submit_otp(self, page: Page, otp: str) -> Dict[str, Any]:
        """OTP kodunu giriş alanına doldurur ve gönderir."""
        result: Dict[str, Any] = {"logged_in": False}

        otp_selector = await self._first_visible(page, OTP_INPUT_SELECTORS, timeout_ms=8000)
        if not otp_selector:
            logger.warning(f"[{self.key}] OTP giriş alanı bulunamadı.")
            return result

        await self._fill_visible(page, OTP_INPUT_SELECTORS, otp)
        await page.wait_for_timeout(2000)

        submitted = await self._click_visible(page, OTP_SUBMIT_SELECTORS)
        if not submitted:
            try:
                js_result = await page.evaluate(
                    """
                    (function(){
                      var bs = document.querySelectorAll('button[type="submit"], button');
                      for (var b of bs){
                        var t = (b.textContent||'').toLowerCase();
                        if (t.includes('verify') || t.includes('doğrula') || t.includes('submit') || b.type==='submit'){
                          b.removeAttribute('disabled'); b.click(); return b.textContent.trim();
                        }
                      }
                      return null;
                    })()
                    """
                )
                submitted = bool(js_result)
            except Exception:
                pass

        await page.wait_for_timeout(5000)

        body_text = (await page.locator("body").inner_text(timeout=10000)).lower()
        current_url = page.url

        if any(k in body_text for k in DASHBOARD_INDICATORS) or (
            "login" not in current_url.lower() and "sign-in" not in current_url.lower()
        ):
            result["logged_in"] = True

        return result

    # ------------------------------------------------------------------ #
    # Yardımcılar
    # ------------------------------------------------------------------ #
    async def _first_visible(self, page: Page, selectors: List[str], timeout_ms: int = 8000):
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.is_visible(timeout=timeout_ms):
                    return sel
            except Exception:
                continue
        return None

    async def _fill_visible(self, page: Page, selectors: List[str], value: str) -> bool:
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.is_visible(timeout=5000):
                    await loc.click()
                    await loc.fill("")
                    for ch in str(value):
                        await page.keyboard.type(ch)
                        await page.wait_for_timeout(30)
                    return True
            except Exception:
                continue
        return False

    async def _click_visible(self, page: Page, selectors: List[str]) -> bool:
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.is_visible(timeout=5000):
                    disabled = await loc.get_attribute("disabled")
                    if disabled is None:
                        await loc.click()
                        return True
            except Exception:
                continue
        return False

    async def _dismiss_cookie_popups(self, page: Page) -> None:
        selectors = [
            'button:has-text("Kabul Et")',
            'button:has-text("Tümünü Kabul Et")',
            'button:has-text("Accept")',
            'button:has-text("I Agree")',
            'button:has-text("Allow All")',
            'button:has-text("Tamam")',
        ]
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.is_visible(timeout=3000):
                    await loc.click()
                    logger.debug(f"[{self.key}] Çerez butonu tıklandı: {sel}")
            except Exception:
                continue

    async def _wait_cloudflare(self, page: Page) -> None:
        """Cloudflare interstitial kısa bir süre için beklenip geçilmeye çalışılır."""
        cf_keywords = ["just a moment", "checking your browser", "bir dakika", "güvenlik doğrulaması"]
        for _ in range(6):
            try:
                body_text = (await page.locator("body").inner_text(timeout=5000)).lower()
            except Exception:
                body_text = ""
            if not any(k in body_text for k in cf_keywords):
                return
            cf_frame = next((f for f in page.frames if "challenges.cloudflare.com" in f.url), None)
            if cf_frame:
                try:
                    fe = await cf_frame.frame_element()
                    bbox = await fe.bounding_box()
                    if bbox and bbox.get("width", 0) > 0:
                        await page.mouse.click(
                            bbox["x"] + bbox["width"] / 2,
                            bbox["y"] + bbox["height"] / 2,
                        )
                        await page.wait_for_timeout(6000)
                        continue
                except Exception:
                    pass
            await page.wait_for_timeout(4000)
