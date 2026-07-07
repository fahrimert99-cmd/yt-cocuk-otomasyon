# 🤖 YouTube Niş Video Otomasyonu — Make + GitHub (Ücretsiz)

**Make senaryonuz zaten oluşturuldu** (adı: *YouTube Nis Video Otomasyonu*).
Bu depo, videoyu **filigransız** üreten ve YouTube'a yükleyen GitHub tarafıdır.

## Nasıl çalışıyor?
```
Make (günlük zamanlayıcı)
   └─ Gemini: niş konu + senaryo + başlık + etiket üretir (JSON)
        └─ HTTP: GitHub'ı tetikler (base64 payload)
              └─ GitHub Actions: edge-tts + alt yazı + FFmpeg ile video
                    └─ YouTube'a yükler
```
Make ağır video dosyasına **hiç dokunmaz** (sadece küçük JSON gider) → Free plan sınırlarına takılmaz. Video render'ı GitHub'da olduğu için **filigran yok, süre/boyut sınırı yok.**

**Maliyet: 0 TL.** Gemini (Make içi, ücretsiz) + edge-tts + FFmpeg + GitHub Actions + YouTube API — hepsi bedava.

---

## KURULUM (tek seferlik)

### 1) Bu depoyu GitHub'a yükle
Yeni bir GitHub reposu aç, bu klasördeki tüm dosyaları içine at.

### 2) YouTube yükleme izni (ücretsiz)
1. https://console.cloud.google.com → yeni proje → "YouTube Data API v3"ü etkinleştir.
2. OAuth consent screen doldur (External, kendi mailini test kullanıcısı ekle).
3. Credentials → OAuth client ID → **Desktop app** → `client_secret.json` indir.
4. Kendi bilgisayarında:
   ```bash
   pip install google-auth-oauthlib
   python3 token_al.py
   ```
   Çıkan **YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN** değerlerini kopyala.

### 3) GitHub Secrets
Repo → Settings → Secrets and variables → Actions → New repository secret:
- `YT_CLIENT_ID`
- `YT_CLIENT_SECRET`
- `YT_REFRESH_TOKEN`

### 4) GitHub kişisel erişim token'ı (Make'in tetiklemesi için)
1. GitHub → Settings → Developer settings → **Personal access tokens (classic)** → Generate.
2. Kapsam (scope): **repo** işaretle. Token'ı kopyala (bir daha gösterilmez).

### 5) Make senaryosunu bağla
1. Make → Scenarios → **YouTube Nis Video Otomasyonu**'nu aç.
2. İkinci modül (**HTTP → Make a request**) içinde iki yeri düzenle:
   - **URL**: `https://api.github.com/repos/KULLANICI/REPO/dispatches`
     → `KULLANICI/REPO` yerine kendi repo yolunu yaz (örn. `fahrimert/yt-otomasyon`).
   - **Authorization header** değeri: `Bearer GITHUB_PAT_BURAYA`
     → `GITHUB_PAT_BURAYA` yerine 4. adımdaki token'ı yapıştır.
3. Kaydet → sağ altta senaryoyu **ON** (aktif) yap.

### 6) Test
- Make'te senaryonun altındaki **Run once** ile elle tetikle.
- GitHub → Actions sekmesinde iş çalışır, video üretilip YouTube'a **private** yüklenir.

Bundan sonra her gün otomatik çalışır (zamanlama Make'te ayarlı).

---

## AYARLAR

### İçerik/format — `config.json` (bu depoda)
```json
{ "format": "dikey", "ses": "kadin", "gizlilik": "private", "kategori": "27" }
```
- format: `dikey` (Shorts) | `yatay`
- ses: `kadin` | `erkek`
- gizlilik: `private` | `unlisted` | `public`
- kategori: 27=Eğitim 28=Bilim 24=Eğlence 22=Blog

### Niş ve senaryo tonu — Make'te
Make senaryosunda **Gemini modülünün "Text prompt"** alanı içeriği belirler.
Nişi değiştirmek için oradaki "Nis: İlginç Bilgiler ve Bilim" ifadesini düzenle.

### Yayın sıklığı — Make'te
Senaryonun zamanlaması şu an **günde bir**. Make'te senaryonun saat ikonundan
(Scheduling) sıklığı değiştirebilirsin (Free planda en sık 15 dakikada bir).

---

## GÖRSELLER
Varsayılan: metinden otomatik degrade başlık kartı (sıfır kaynak). İstersen
`assets/` klasörüne telifsiz `.jpg/.png` (Pexels/Pixabay) koy → Ken Burns zoom ile kullanılır.

---

## ÖNERİ
İlk hafta `"gizlilik": "private"` kalsın. Üretilenleri kontrol et, niş/ses/süreyi oturt,
sonra `"public"` yap. Böylece kaliteyi kaybetmeden otomasyonu güvenle devreye alırsın.

## GÜVENLİK
GitHub token'ını ve YouTube anahtarlarını sadece Secrets / Make modülüne gir; düz metin olarak repoya koyma. `client_secret.json`'u repoya yükleme.
