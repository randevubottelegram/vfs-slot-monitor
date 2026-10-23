# -*- coding: utf-8 -*-
"""VFS Randevu Slot Takip Botu — giriş noktası.

Özellikler:
  - /start : Ülke seçme menüsü
  - /durum : Seçili ülkenin güncel slot durumunu gösterir
  - /durdur : Takibi durdurur
  - /devam : Takibi yeniden başlatır
  - /ayarlar : Kontrol aralığı ve bildirim ayarları
  - Arka planda seçili ülke için her X saniyede bir VFS sayfası kontrol edilir;
    durum değiştiğinde (özellikle randevu açıldığında) Telegram'a mesaj atılır.

Çalıştırma:
  pip install -r requirements.txt
  cp .env.example .env   # TELEGRAM_BOT_TOKEN doldurun
  python main.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional

from aiohttp import web

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import (
    BASE_DIR,
    CHECK_INTERVAL_SECONDS,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    find_country,
    find_country_by_name,
    get_credentials,
    load_countries,
)
from monitor import VFSMonitor
from notifier import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("vfs-bot")

STATE_DIR = BASE_DIR / "state"
COUNTRIES = load_countries()


# ====================================================================== #
# Durum / denetleyici
# ====================================================================== #
class BotController:
    """Botun çalışma durumunu (seçili ülke, monitör, sayaç) tutar."""

    def __init__(self) -> None:
        self.selected_country_key: Optional[str] = None
        self.monitor: Optional[VFSMonitor] = None
        self.running: bool = False
        self.notifier: Optional[TelegramNotifier] = None
        self._loop_task: Optional[asyncio.Task] = None

    def select_country(self, key: str) -> Optional[Dict]:
        country = find_country(COUNTRIES, key)
        if not country:
            return None
        self.selected_country_key = key
        credentials = get_credentials(country)
        self.monitor = VFSMonitor(
            country,
            STATE_DIR,
            headless=True,
            credentials=credentials,
        )
        self.running = True
        return country

    def stop(self) -> None:
        self.running = False
        self.selected_country_key = None
        self.monitor = None

    def resume(self) -> bool:
        if not self.selected_country_key:
            return False
        country = find_country(COUNTRIES, self.selected_country_key)
        if country:
            credentials = get_credentials(country)
            self.monitor = VFSMonitor(
                country,
                STATE_DIR,
                headless=True,
                credentials=credentials,
            )
            self.running = True
            return True
        return False


controller = BotController()

# Notifier — token yoksa mesaj atamaz ama uyarı verir
notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
controller.notifier = notifier


# ====================================================================== #
# Klavye / menü yardımcıları
# ====================================================================== #
def country_keyboard() -> InlineKeyboardMarkup:
    """Ülke seçim inline klavyesi (2 sütunlu)."""
    keyboard = []
    row = []
    for c in COUNTRIES:
        row.append(
            InlineKeyboardButton(
                f"{c.get('flag','')} {c.get('name')}",
                callback_data=f"select:{c.get('key')}",
            )
        )
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("❌ Takibi Durdur", callback_data="action:stop")])
    return InlineKeyboardMarkup(keyboard)


def status_text(country: Dict, status: str, detail: str) -> str:
    emoji = {"OPEN": "✅", "CLOSED": "❌", "ERROR": "⚠️", "UNKNOWN": "🟡"}.get(
        status.upper(), "🟡"
    )
    return (
        f"{emoji} *{country.get('flag','')} {country.get('name')} — Slot Durumu*\n\n"
        f"🚦 *Durum:* {status.upper()}\n"
        f"📝 {detail}\n"
        f"🔗 {country.get('url','')}\n"
    )


# ====================================================================== #
# Telegram komutları
# ====================================================================== #
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "👋 *VFS Randevu Slot Takip Botuna Hoş Geldiniz*\n\n"
        "Aşağıdan takip etmek istediğiniz ülkeyi seçin. "
        "Randevu slotu açıldığında (durum OPEN olduğunda) size buradan bildirim gönderirim.\n\n"
        "İlk olarak bir ülke seçmelisiniz."
    )
    await update.message.reply_text(
        text, reply_markup=country_keyboard(), parse_mode=ParseMode.MARKDOWN
    )


async def cmd_durum(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not controller.selected_country_key or not controller.monitor:
        await update.message.reply_text(
            "Henüz bir ülke seçilmemiş. /start komutuyla ülke seçin.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    country = find_country(COUNTRIES, controller.selected_country_key)
    if not country:
        await update.message.reply_text("Ülke bulunamadı.")
        return
    await update.message.reply_text("🔍 Durum kontrol ediliyor, lütfen bekleyin...")
    result = await controller.monitor.check_once()
    await update.message.reply_text(
        status_text(country, result["status"], result["detail"]),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_durdur(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    was_running = controller.running
    controller.stop()
    if was_running:
        await update.message.reply_text("⏹️ Slot takibi durduruldu. /devam ile yeniden başlatabilirsiniz.")
    else:
        await update.message.reply_text("Zaten durdurulmuş durumda.")


async def cmd_devam(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if controller.resume():
        await update.message.reply_text("▶️ Slot takibi yeniden başlatıldı.")
    else:
        await update.message.reply_text(
            "Önce /start ile bir ülke seçmeniz gerekiyor.",
            parse_mode=ParseMode.MARKDOWN,
        )


async def cmd_ayarlar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    key = controller.selected_country_key or "Yok"
    country = find_country(COUNTRIES, key) if key != "Yok" else None
    name = country.get("name") if country else "Seçilmedi"
    text = (
        "⚙️ *Bot Ayarları*\n\n"
        f"🌍 Seçili ülke: {name}\n"
        f"⏱️ Kontrol aralığı: {CHECK_INTERVAL_SECONDS} saniye\n"
        f"▶️ Çalışıyor mu: {'Evet' if controller.running else 'Hayır'}\n\n"
        "Aralığı değiştirmek için .env dosyasındaki CHECK_INTERVAL_SECONDS değerini düzenleyip botu yeniden başlatın."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kendi chat ID'nizi öğrenmek için (.env'e girmek üzere)."""
    await update.message.reply_text(
        f"🆔 Sohbet ID'niz: `{update.effective_chat.id}`\n"
        "Bu değeri .env dosyasındaki TELEGRAM_CHAT_ID'ye yazabilirsiniz.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ====================================================================== #
# Inline buton callbackleri
# ====================================================================== #
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data.startswith("select:"):
        key = data.split(":", 1)[1]
        country = controller.select_country(key)
        if country:
            controller.notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
            await query.edit_message_text(
                f"✅ {country.get('flag','')} {country.get('name')} seçildi. "
                f"Takip arkaplanda başlatıldı (her {CHECK_INTERVAL_SECONDS}s'de bir).",
                parse_mode=ParseMode.MARKDOWN,
            )
            # Başlangıç bildirimi
            if notifier.token and TELEGRAM_CHAT_ID:
                notifier.send_startup(country["name"], country.get("flag", ""), CHECK_INTERVAL_SECONDS, chat_id=TELEGRAM_CHAT_ID)
            else:
                logger.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID eksik — bildirimler gönderilemeyecek.")
        else:
            await query.edit_message_text("Ülke seçilemedi, tekrar deneyin.")
        return

    if data == "action:stop":
        controller.stop()
        await query.edit_message_text(
            "⏹️ Slot takibi durduruldu. /devam ile yeniden başlatabilirsiniz.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await query.edit_message_text("Bilinmeyen işlem.")


# ====================================================================== #
# Arka plan monitoring döngüsü
# ====================================================================== #
async def run_check_and_notify(bot) -> None:
    """Tek seferlik kontrol + durum değişimi bildirimi."""
    if not controller.selected_country_key or not controller.monitor or not controller.running:
        return

    country = find_country(COUNTRIES, controller.selected_country_key)
    if not country:
        return

    state_path = STATE_DIR / f"state_{controller.selected_country_key}.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    except Exception:
        state = {}

    result = await controller.monitor.check_once()
    new_status = result.get("status", "UNKNOWN")
    new_detail = result.get("detail", "")
    last_status = state.get("last_status")
    open_alert_count = int(state.get("open_alert_count", 0))
    waitlist_alert_count = int(state.get("waitlist_alert_count", 0))

    should_notify = False
    message = ""

    if new_status != last_status:
        # Durum değişti → her zaman bildir
        should_notify = True
        if new_status.upper() == "OPEN":
            message = (
                f"🎉 *RANDEVU SLOTU AÇILDI!*\n\n"
                f"{country.get('flag','')} {country.get('name')}\n"
                f"📝 {new_detail}\n"
                f"🔗 {country.get('url','')}"
            )
            open_alert_count = 0
            waitlist_alert_count = 0
        elif new_status.upper() == "WAITLIST":
            message = (
                f"⏳ *BEKLEME LISTESİ AÇILDI!*\n\n"
                f"{country.get('flag','')} {country.get('name')}\n"
                f"📝 {new_detail}\n"
                f"🔗 {country.get('url','')}\n\n"
                f"Bekleme listesine kaydolabilirsiniz."
            )
            open_alert_count = 0
        elif new_status.upper() == "CLOSED":
            message = (
                f"❌ *Slot kapatıldı*\n\n"
                f"{country.get('flag','')} {country.get('name')}\n"
                f"📝 {new_detail}\n"
                f"🔗 {country.get('url','')}"
            )
            open_alert_count = 0
            waitlist_alert_count = 0
        elif new_status.upper() == "LOGIN_FORM":
            message = (
                f"🔐 *Giriş Gerekli*\n\n"
                f"{country.get('flag','')} {country.get('name')}\n"
                f"📝 {new_detail}\n"
                f"🔗 {country.get('url','')}\n\n"
                f"Bu ülkede slot görmek için VFS'e giriş gerekli. "
                f".env'de VFS_{country.get('key','').upper()}_EMAIL ve _PASSWORD tanımlayın."
            )
            open_alert_count = 0
            waitlist_alert_count = 0
        elif new_status.upper() == "NEEDS_OTP":
            message = (
                f"🔑 *OTP Gerekli*\n\n"
                f"{country.get('flag','')} {country.get('name')}\n"
                f"📝 {new_detail}\n"
                f"🔗 {country.get('url','')}\n\n"
                f".env'de VFS_{country.get('key','').upper()}_IMAP_APP_PASSWORD tanımlayın."
            )
            open_alert_count = 0
            waitlist_alert_count = 0
        elif new_status.upper() == "CF_CHALLENGE":
            message = (
                f"☁️ *Cloudflare Engeli*\n\n"
                f"{country.get('flag','')} {country.get('name')}\n"
                f"📝 {new_detail}\n"
                f"🔗 {country.get('url','')}"
            )
            open_alert_count = 0
            waitlist_alert_count = 0
        else:
            message = (
                f"⚠️ *Durum değişti*\n\n"
                f"{country.get('flag','')} {country.get('name')}\n"
                f"🚦 {new_status.upper()}\n"
                f"📝 {new_detail}\n"
                f"🔗 {country.get('url','')}"
            )
            open_alert_count = 0
            waitlist_alert_count = 0
    elif new_status.upper() == "OPEN":
        # Hala açık → her 6 kontrolde bir hatırlatma (≈ 30 dk @ 5sn aralık)
        open_alert_count += 1
        if open_alert_count % 6 == 0:
            should_notify = True
            message = (
                f"⏰ *Slot hâlâ açık*\n\n"
                f"{country.get('flag','')} {country.get('name')}\n"
                f"📝 {new_detail}\n"
                f"🔗 {country.get('url','')}"
            )
    elif new_status.upper() == "WAITLIST":
        # Hala bekleme listesi açık → her 6 kontrolde bir hatırlatma
        waitlist_alert_count += 1
        if waitlist_alert_count % 6 == 0:
            should_notify = True
            message = (
                f"⏳ *Bekleme listesi hâlâ açık*\n\n"
                f"{country.get('flag','')} {country.get('name')}\n"
                f"📝 {new_detail}\n"
                f"🔗 {country.get('url','')}"
            )

    # Kalıcı durumu güncelle
    state.update(
        {
            "last_status": new_status,
            "last_detail": new_detail,
            "open_alert_count": open_alert_count,
            "waitlist_alert_count": waitlist_alert_count,
            "country": country.get("name"),
            "key": controller.selected_country_key,
        }
    )
    try:
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        logger.warning(f"State kaydedilemedi: {exc}")

    if should_notify and message and notifier.token and TELEGRAM_CHAT_ID:
        ok = notifier.send_message(message, chat_id=TELEGRAM_CHAT_ID)
        if ok:
            logger.info(f"[{controller.selected_country_key}] Bildirim gönderildi: {new_status}")
        else:
            logger.warning(f"[{controller.selected_country_key}] Bildirim gönderilemedi.")


async def monitoring_loop(application: Application) -> None:
    """Sürekli çalışan arka plan döngüsü."""
    logger.info("Arka plan monitoring döngüsü başlatıldı.")
    while True:
        try:
            await run_check_and_notify(application.bot)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Monitoring döngüsü hatası: {exc}")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


async def post_init(application: Application) -> None:
    """Bot başlatıldıktan sonra arka plan döngüsünü başlatır."""
    asyncio.create_task(monitoring_loop(application))


# ====================================================================== #
# Mesaj yakalama (yazılı ülke ismi desteği)
# ====================================================================== #
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    if text.startswith("/"):
        return
    country = find_country_by_name(COUNTRIES, text)
    if country:
        controller.select_country(country["key"])
        await update.message.reply_text(
            f"✅ {country.get('flag','')} {country.get('name')} seçildi (yazılı komutla). "
            "Takip arkaplanda çalışıyor.",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text(
            "Ülke ismi tanınmadı. Lütfen /start ile menüden bir ülke seçin "
            "ya da ülke adını Türkçe/İngilizce yazın.",
            parse_mode=ParseMode.MARKDOWN,
        )


# ====================================================================== #
# Ana giriş
# ====================================================================== #
def build_application() -> Application:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN .env'de tanımlanmamış! Bot çalışmayacak.")
    builder = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).post_init(post_init)
    app = builder.build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("durum", cmd_durum))
    app.add_handler(CommandHandler("durdur", cmd_durdur))
    app.add_handler(CommandHandler("devam", cmd_devam))
    app.add_handler(CommandHandler("ayarlar", cmd_ayarlar))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    return app


async def main() -> None:
    app = build_application()
    logger.info("Web sunucusu başlatılıyor...")
    runner = await start_web_server()
    logger.info("Bot polling başlatılıyor... (Çıkmak için Ctrl+C)")
    try:
        await app.run_polling(allowed_updates=Update.ALL_TYPES)
    finally:
        await runner.cleanup()


async def health_handler(request):
    return web.Response(text="OK")


async def start_web_server():
    app_web = web.Application()
    app_web.router.add_get("/health", health_handler)
    runner = web.AppRunner(app_web)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Web sunucusu 0.0.0.0:{port} portunda çalışıyor")
    return runner


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Kullanıcı tarafından durduruldu.")
