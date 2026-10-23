# -*- coding: utf-8 -*-
"""Hollanda Cloudflare challenge'ını incele ve aşmaya çalış."""

import asyncio
import sys

sys.path.insert(0, "vfs-slot-monitor")
from camoufox.async_api import AsyncCamoufox


async def main():
    url = "https://visa.vfsglobal.com/tur/en/nld/login"
    
    # Önce headless=True dene, sonra headless=False
    for headless in [True, False]:
        print(f"\n{'='*70}")
        print(f"🔍 Hollanda deneme: headless={headless}")
        print(f"{'='*70}")
        
        async with AsyncCamoufox(headless=headless) as browser:
            page = await browser.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(10000)
                
                body_text = await page.locator("body").inner_text(timeout=10000)
                title = await page.title()
                print(f"📄 Başlık: {title}")
                print(f"📝 Body: {body_text[:500]}")
                
                # Turnstile iframe var mı?
                cf_frame = next(
                    (f for f in page.frames if 'challenges.cloudflare.com' in f.url), None
                )
                print(f"☁️  Cloudflare Frame: {'VAR' if cf_frame else 'YOK'}")
                
                if cf_frame:
                    # Turnstile checkbox var mı?
                    try:
                        cb = cf_frame.locator('input[type="checkbox"]')
                        cb_count = await cb.count()
                        print(f"🔘 Checkbox sayısı: {cb_count}")
                        
                        if cb_count > 0:
                            checked = await cb.get_attribute("aria-checked")
                            print(f"🔘 Checkbox checked: {checked}")
                            
                            # Checkbox'a tıkla
                            fe = await cf_frame.frame_element()
                            bbox = await fe.bounding_box()
                            if bbox and bbox.get('width', 0) > 0:
                                print(f"🖱️  Turnstile tıklanıyor: ({bbox['x']+bbox['width']/2:.0f}, {bbox['y']+bbox['height']/2:.0f})")
                                await page.mouse.click(
                                    bbox['x'] + bbox['width'] / 2,
                                    bbox['y'] + bbox['height'] / 2
                                )
                                await page.wait_for_timeout(8000)
                                
                                # Kontrol et
                                body_after = await page.locator("body").inner_text(timeout=10000)
                                title_after = await page.title()
                                print(f"\n✅ Tıklama sonrası:")
                                print(f"📄 Başlık: {title_after}")
                                print(f"📝 Body (ilk 500): {body_after[:500] if body_after else 'boş'}")
                                
                                # Form elemanı
                                try:
                                    form_count = await page.locator("input, select, textarea, button").count()
                                    print(f"🔢 Form Elemanı: {form_count}")
                                except Exception as e:
                                    print(f"🔢 Form Elemanı: hata - {e}")
                    except Exception as e:
                        print(f"❌ Turnstile işlem hatası: {e}")
                
                # Cloudflare challenge hala devam ediyor mu?
                if "just a moment" in body_text.lower() or "checking your browser" in body_text.lower():
                    print("\n⏳ Cloudflare challenge hala aktif, 15s bekleniyor...")
                    await page.wait_for_timeout(15000)
                    body_final = await page.locator("body").inner_text(timeout=10000)
                    title_final = await page.title()
                    print(f"📄 Nihai Başlık: {title_final}")
                    print(f"📝 Nihai Body (ilk 500): {body_final[:500] if body_final else 'boş'}")
                    
            except Exception as exc:
                print(f"❌ HATA: {type(exc).__name__}: {exc}")
            finally:
                await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
