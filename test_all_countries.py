# -*- coding: utf-8 -*-
"""Tüm ülkeleri sırayla test eder. Camoufox ile girişsiz slot kontrolü."""

import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, "vfs-slot-monitor")
from config import load_countries
from monitor import VFSMonitor


async def test_country(country, idx, total, state_dir="/tmp/vfs_country_test"):
    key = country.get("key")
    name = country.get("name")
    url = country.get("url")
    flag = country.get("flag", "")

    print(f"\n{'='*60}")
    print(f"[{idx}/{total}] {flag} {name} ({key})")
    print(f"URL: {url}")
    print(f"{'='*60}")

    m = VFSMonitor(country, state_dir, headless=True)
    try:
        result = await m.check_once()
        status = result.get("status", "UNKNOWN")
        detail = result.get("detail", "")
        matched = result.get("matched", "-")

        # Renkli durum emoji
        status_emoji = {
            "OPEN": "✅",
            "WAITLIST": "⏳",
            "CLOSED": "❌",
            "ERROR": "⚠️",
            "UNKNOWN": "🟡",
        }.get(status, "🟡")

        print(f"\n📊 SONUÇ: {status_emoji} {status}")
        print(f"📝 Detay: {detail}")
        print(f"🔍 Eşleşen: {matched}")
        return {
            "key": key,
            "name": name,
            "flag": flag,
            "status": status,
            "detail": detail,
            "matched": matched,
            "url": url,
        }
    except Exception as exc:
        print(f"\n❌ HATA: {type(exc).__name__}: {exc}")
        return {
            "key": key,
            "name": name,
            "flag": flag,
            "status": "ERROR",
            "detail": str(exc),
            "matched": "-",
            "url": url,
        }
    finally:
        await m.stop()


async def main():
    countries = load_countries("vfs-slot-monitor/countries.json")
    total = len(countries)
    print(f"🔍 {total} ülke test edilecek...\n")

    results = []
    for idx, country in enumerate(countries, 1):
        res = await test_country(country, idx, total)
        results.append(res)
        # Ülkeler arasında kısa bekleme (VFS engellemesini azaltmak için)
        if idx < total:
            print("\n⏳ Bir sonraki ülkeye geçiliyor (5s bekleme)...")
            await asyncio.sleep(5)

    # Özet rapor
    print("\n" + "=" * 60)
    print("📋 TEST ÖZET RAPORU")
    print("=" * 60)

    open_count = sum(1 for r in results if r["status"] == "OPEN")
    waitlist_count = sum(1 for r in results if r["status"] == "WAITLIST")
    closed_count = sum(1 for r in results if r["status"] == "CLOSED")
    error_count = sum(1 for r in results if r["status"] == "ERROR")
    unknown_count = sum(1 for r in results if r["status"] == "UNKNOWN")

    print(f"\n✅ OPEN (slot var): {open_count}")
    print(f"⏳ WAITLIST (bekleme listesi): {waitlist_count}")
    print(f"❌ CLOSED (kapalı): {closed_count}")
    print(f"🟡 UNKNOWN (netleşemedi): {unknown_count}")
    print(f"⚠️ ERROR (hata): {error_count}")

    print("\n--- Detaylı Liste ---")
    for r in results:
        emoji = {
            "OPEN": "✅",
            "WAITLIST": "⏳",
            "CLOSED": "❌",
            "ERROR": "⚠️",
            "UNKNOWN": "🟡",
        }.get(r["status"], "🟡")
        print(f"  {emoji} {r['flag']} {r['name']} ({r['key']}): {r['status']} — {r['detail'][:80]}")

    # Sonuç dosyası
    import json
    with open("test_sonuclari.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "test_tarihi": datetime.now().isoformat(),
                "toplam": total,
                "open": open_count,
                "waitlist": waitlist_count,
                "closed": closed_count,
                "unknown": unknown_count,
                "error": error_count,
                "sonuclar": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print("\n💾 Detaylı sonuç 'test_sonuclari.json' dosyasına kaydedildi.")


if __name__ == "__main__":
    asyncio.run(main())
