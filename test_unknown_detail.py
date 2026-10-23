# -*- coding: utf-8 -*-
"""UNKNOWN olan 5 ülkeyi detaylı incele: final URL, başlık, body, CF kuyruğu."""

import asyncio
import sys
import os

sys.path.insert(0, "vfs-slot-monitor")
from config import load_countries
from monitor import VFSMonitor
from camoufox.async_api import AsyncCamoufox


async def inspect_country(country):
    key = country.get("key")
    name = country.get("name")
    url = country.get("url")

    print(f"\n{'='*70}")
    print(f"🔍 {country.get('flag','')} {name} ({key})")
    print(f"URL: {url}")
    print(f"{'='*70}")

    async with AsyncCamoufox(headless=True) as browser:
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass

            # Dinamik içerik için ekstra bekleme
            await page.wait_for_timeout(8000)

            final_url = page.url
            title = await page.title()
            body_text = ""
            try:
                body_text = await page.locator("body").inner_text(timeout=10000)
            except Exception as exc:
                body_text = f"[Body alınamadı: {exc}]"

            body_lower = body_text.lower()

            # Cloudflare kuyruk tespiti
            cf_queue_keywords = [
                "estimated wait time", "virtual queue", "waiting room",
                "you are now in line", "high volume of traffic",
                "queue-it", "queueit", "this page will automatically refresh",
            ]
            cf_found = [k for k in cf_queue_keywords if k in body_lower]

            # Form elemanı
            try:
                form_count = await page.locator("input, select, textarea, button").count()
            except Exception:
                form_count = -1

            print(f"\n🌐 Final URL: {final_url}")
            print(f"📄 Sayfa Başlığı: {title}")
            print(f"📝 Body Uzunluğu: {len(body_text)} karakter")
            print(f"🔢 Form Elemanı: {form_count}")
            print(f"☁️  Cloudflare Kuyruk Anahtar Kelimeleri: {cf_found if cf_found else 'Yok'}")

            print(f"\n📄 BODY (ilk 1500 karakter):")
            print(body_text[:1500])

            if len(body_text) > 1500:
                print(f"\n📄 BODY (son 1000 karakter):")
                print(body_text[-1000:])

        except Exception as exc:
            print(f"\n❌ HATA: {type(exc).__name__}: {exc}")
        finally:
            await browser.close()


async def main():
    countries = load_countries("vfs-slot-monitor/countries.json")
    unknown_keys = ["netherlands", "austria", "switzerland", "iceland", "luxembourg", "bulgaria"]

    for c in countries:
        if c.get("key") in unknown_keys:
            await inspect_country(c)
            print("\n⏳ Bir sonraki ülkeye geçiliyor (5s)...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
