# VFS Randevu Slot Takip Botu

Telegram üzerinden **VFS Global randevu slotlarını** takip eden, **ülke seçebileceğiniz** ve slot / bekleme listesi açıldığında size **bildirim gönderen** basit, modüler bir Python uygulamasıdır.

## Ne yapar?

- 🌍 İstediğiniz ülkeyi seçersiniz (Fransa, Hollanda, İsveç, Polonya, vb.)
- 🔍 Arka planda VFS randevu sayfasını düzenli aralıklarla kontrol eder
- 📩 Randevu slotu açıldığında (**OPEN**) veya **bekleme listesi açıldığında (WAITLIST)** size Telegram ile bildirim gönderir
- 🔁 Durum değiştiğinde (açık → kapalı, hata vb.) da haberdar olur
- 💾 Son durumu `state/` klasöründe hatırlar, böylece aynı uyarıyı tekrar atmamak için
- 🔐 Giriş gerektiren ülkelerde (Hollanda, Norveç vb.) VFS'e otomatik giriş yapıp, **Gmail IMAP üzerinden OTP alıp** dashboard'da slot kontrolü yapar

## Durum Özeti (19 ülke test edildi)

| Durum | Sayı | Ülkeler |
|-------|------|---------|
| ✅ OPEN | 15 | Fransa, Danimarka, İsveç, Avusturya, Belçika, Çekya, Estonya, Finlandiya, İsviçre, İzlanda, Letonya, Litvanya, Lüksemburg, Malta, Bulgaristan |
| 🔐 LOGIN_FORM | 2 | Hollanda, Norveç (giriş gerekiyor) |
| ⚠️ ERROR | 1 | İspanya BLS (DNS erişim hatası) |

Hollanda ve Norveç'te slot takvimi yalnızca **VFS'e giriş yaptıktan sonra** görünür. Bu ülkeleri takip etmek isterseniz `.env`'de VFS e-posta/şifre ve Gmail **Uygulama Şifresi** (IMAP) tanımlamalısınız.

## Kurulum

### 1. Sanal ortam oluşturun ve bağımlılıkları yükleyin

```bash
cd vfs-slot-monitor
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
```

Camoufox ilk çalıştırmada kendi tarayıcı binary'sini indirir (yaklaşık 1 GB, tek seferlik).

### 2. Telegram botu oluşturun

1. Telegram'da **@BotFather** ile bir bot oluşturun (`/newbot`).
2. Alınan **Bot Token**'u not edin.
3. Botu başlatın ve kendi **Chat ID'nizi** öğrenin (botunuza `/id` yazın ya da [@userinfobot](https://t.me/userinfobot) ile öğrenin).

### 3. Gmail Uygulama Şifresi oluşturun (Hollanda/Norveç için gerekli)

Hollanda ve Norveç'te slot görmek için VFS'e giriş gerekir. Giriş sonrası VFS size **OTP (tek seferlik kod)** gönderir; bu kodu bot Gmail IMAP üzerinden otomatik okur.

1. Gmail hesabınızda **2FA (iki aşamalı doğrulama)**'yı açın.
2. Google Hesap Ayarları → Güvenlik → **Uygulama şifreleri**'ne gidin.
3. "Posta" için bir uygulama şifresi oluşturun (16 haneli).
4. Bu şifreyi `.env`'de `VFS_NETHERLANDS_IMAP_APP_PASSWORD` veya `VFS_NORWAY_IMAP_APP_PASSWORD` olarak kullanın.

### 4. `.env` dosyasını hazırlayın

```bash
cp .env.example .env
```

`.env` dosyasını düzenleyin:

```
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=123456789
CHECK_INTERVAL_SECONDS=300

# Hollanda için giriş (gerekli):
VFS_NETHERLANDS_EMAIL=ornek@gmail.com
VFS_NETHERLANDS_PASSWORD=sifreniz
VFS_NETHERLANDS_IMAP_APP_PASSWORD=gmail_uygulama_sifreniz

# Norveç için giriş (gerekli):
VFS_NORWAY_EMAIL=ornek@gmail.com
VFS_NORWAY_PASSWORD=sifreniz
VFS_NORWAY_IMAP_APP_PASSWORD=gmail_uygulama_sifreniz

# Diğer ülkeler için de aynı kalıpla eklenebilir:
# VFS_FR_EMAIL=...
# VFS_FR_PASSWORD=...
# VFS_FR_IMAP_APP_PASSWORD=...
```

- `TELEGRAM_BOT_TOKEN`: BotFather'dan aldığınız token.
- `TELEGRAM_CHAT_ID`: Bildirimlerin gideceği sohbet ID'niz (kendi ID'niz).
- `CHECK_INTERVAL_SECONDS`: Kaç saniyede bir kontrol yapılacağı (varsayılan 300 = 5 dakika). Çok kısa aralık VFS tarafından engellenebilir.

### 5. Çalıştırın

```bash
.venv/bin/python main.py
```

Telegram'da `/start` yazın, menüden ülke seçin. Seçtiğiniz ülke için arka planda takip başlar ve slot / bekleme listesi açıldığında size mesaj gelir.

## Komutlar

| Komut | Açıklama |
|-------|----------|
| `/start` | Ülke seçim menüsünü açar |
| `/durum` | Seçili ülkenin anlık slot durumunu kontrol eder |
| `/durdur` | Takibi durdurur |
| `/devam` | Durdurulan takibi yeniden başlatır |
| `/ayarlar` | Mevcut ayarları gösterir |
| `/id` | Kendi sohbet ID'nizi gösterir (.env için) |

## Bildirim türleri

| Durum | Emoji | Anlamı |
|-------|-------|--------|
| `OPEN` | ✅ | Randevu slotu açık (randevu alınabilir) |
| `WAITLIST` | ⏳ | Bekleme listesi açık (kaydolabilirsiniz) |
| `CLOSED` | ❌ | Slot yok / kapalı |
| `LOGIN_FORM` | 🔐 | Sadece giriş formu görünüyor (VFS'e giriş gerekli) |
| `NEEDS_OTP` | 🔑 | OTP kodu gerekiyor (.env'de IMAP şifresi eksik) |
| `CF_CHALLENGE` | ☁️ | Cloudflare koruması sayfayı engelliyor |
| `ERROR` | ⚠️ | Kontrol sırasında hata |
| `UNKNOWN` | 🟡 | Durum netleşemedi |

Durum değiştiğinde anında, aynı durum devam ediyorsa her 6 kontrolde bir hatırlatma gönderilir.

## Dosya yapısı

```
vfs-slot-monitor/
├── main.py              # Giriş noktası — Telegram bot + monitoring döngüsü
├── config.py            # Ülke listesi, .env ve yardımcı fonksiyonlar
├── monitor.py           # Camoufox tabanlı VFS slot kontrolü (girişli/girişsiz)
├── notifier.py          # Telegram bildirimleri
├── otp.py               # Gmail IMAP üzerinden OTP okuma
├── countries.json       # Ülke ve VFS URL tanımları (19 ülke)
├── .env.example         # Ortam değişkenleri örneği
├── requirements.txt     # Python bağımlılıkları
├── state/               # Kalıcı durum dosyaları (otomatik oluşur)
└── README.md            # Bu dosya
```

## Ülke seçimi

`/start` menüsünden ülke seçebilir ya da ülke adını doğrudan yazabilirsiniz (ör. `Fransa`, `Polonya`, `Hollanda`). Desteklenen ülkeler `countries.json` dosyasında tanımlıdır; yeni bir ülke eklemek isterseniz buraya VFS URL'sini ekleyin:

```json
{
  "key": "yeni_ulke",
  "name": "Ülke Adı",
  "flag": "🏳️",
  "provider": "VFS",
  "url": "https://visa.vfsglobal.com/.../login",
  "group": "schengen"
}
```

## GitHub'a Yükleme

```bash
cd vfs-slot-monitor
git init
git add .
git commit -m "İlk commit: VFS slot takip botu"
git remote add origin https://github.com/KULLANICI_ADI/vfs-slot-monitor.git
git push -u origin main
```

`.env`, `state/`, `.venv/` ve `__pycache__/` dosyaları `.gitignore`'a dahil edilmiştir (hassas bilgi içermezler).

## Render Üzerinde Çalıştırma (7/24 — Ücretsiz)

Render'ın ücretsiz planı 15 dakika inaktiflik sonrası uyur. **UptimeRobot** ile her 5 dakikada bir `/health` endpoint'ine ping atarak bu durumu önleyebilirsiniz:

### 1. Render'a Bağlayın

1. [render.com](https://render.com) hesabı oluşturun.
2. "New Web Service" → "Connect a GitHub repository" → `vfs-slot-monitor` repoyu seçin.
3. Ayarlar:
   - **Runtime:** Docker
   - **Plan:** Free
   - **Region:** Frankfurt (veya size yakın)
   - **Build Command:** `pip install -r requirements.txt && playwright install chromium`
   - **Start Command:** `python main.py`
4. **Environment Variables** ekleyin (`.env` dosyasındaki tüm değerleri):
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `CHECK_INTERVAL_SECONDS` (= 300)
   - `VFS_NETHERLANDS_EMAIL`, `VFS_NETHERLANDS_PASSWORD`, `VFS_NETHERLANDS_IMAP_APP_PASSWORD`
   - `VFS_NORWAY_EMAIL`, `VFS_NORWAY_PASSWORD`, `VFS_NORWAY_IMAP_APP_PASSWORD`

### 2. UptimeRobot ile Canlı Tutun

1. [uptimerobot.com](https://uptimerobot.com) hesabı oluşturun.
2. "Add New Monitor" → **HTTP(s)** seçin.
3. Ayarlar:
   - **Friendly Name:** VFS Bot Health
   - **URL:** `https://UYGULAMA_ADINIZ.onrender.com/health`
   - **Monitoring Interval:** 5 dakika
   - **Alert Contacts:** Kendi e-postanızı ekleyin
4. Monitor'u kaydedin.

Bu sayede Render'ın 15 dakikalık uyuma sınırı aşılmış olur ve bot 7/24 çalışır.

> **Not:** Render'ın ücretsiz planında aylık 750 saat kullanım kotası vardır. Normal kullanım bu kotaları aşmaz.


## Önemli notlar

1. **Hollanda / Norveç:** Bu ülkelerde slot takvimi yalnızca VFS'e giriş yaptıktan sonra görünür. `.env`'de VFS e-posta/şifre ve Gmail Uygulama Şifresi tanımlamalısınız. Bot otomatik giriş yapıp IMAP'tan OTP alacaktır.
2. **Cloudflare Waiting Room:** Bazı VFS sayfaları virtual queue gösterir. Bot sayfayı yenileyerek kuyruktan çıkmaya çalışır.
3. **Çalışma aralığı:** 5 dakika veya üzeri önerilir. Daha sık kontrol VFS tarafından engellenecektir.
4. **Headless:** Tarayıcı arka planda çalışır. Görmek isterseniz `main.py`'deki `VFSMonitor(..., headless=True)`'yi `headless=False` yapın.

## Katkı

Yeni ülke, sağlayıcı (BLS, AS-Visa) veya bildirim kanalı eklemek için pull request açabilirsiniz.

## Lisans

MIT
