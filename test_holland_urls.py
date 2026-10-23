# -*- coding: utf-8 -*-
"""Hollanda için farklı VFS URL pattern'leri dene."""

import asyncio
import sys

sys.path.insert(0, "vfs-slot-monitor")
from camoufox.async_api import AsyncCamoufox

URLS = [
    "https://visa.vfsglobal.com/tur/en/nld/login",
    "https://visa.vfsglobal.com/nld/en/login",
    "https://visa.vfsglobal.com/tur/nld/login",
    "https://visa.vfsglobal.com/en/nld/login",
]


async def test_url(url, headless=True):
    print(f"\n{'='*70}")
    print(f"🔍 URL: {url} (headless={headless})")
    print(f"{'='*70}")
    
    async with AsyncCamoufox(headless=headless) as browser:
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(8000)
            
            body_text = await page.locator("body").inner_text(timeout=10000)
            title = await page.title()
            final_url = page.url
            
            print(f"🌐 Final URL: {final_url}")
            print(f"📄 Başlık: {title}")
            print(f"📝 Body (ilk 500): {body_text[:500] if body_text else 'boş'}")
            
            # Form elemanı
            try:
                form_count = await page.locator("input, select, textarea, button").count()
                print(f"🔢 Form Elemanı: {form_count}")
            except Exception as e:
                print(f"🔢 Form Elemanı: hata - {e}")
            
            # Cloudflare challenge mı?
            if "just a moment" in body_text.lower() or "checking your browser" in body_text.lower():
                print(f"☁️  Cloudflare Challenge: EVET")
            elif "login" in title.lower():
                print(f"☁️  Cloudflare Challenge: Hayır (Login sayfası)")
            else:
                print(f"☁️  Cloudflare Challenge: Bilinmiyor")
                
        except Exception as exc:
            print(f"❌ HATA: {type(exc).__name__}: {exc}")
        finally:
            await browser.close()


async def main():
    for url in URLS:
        await test_url(url, headless=True)
        print("\n⏳ Bir sonraki URL'ye geçiliyor (3s)...")
        await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
