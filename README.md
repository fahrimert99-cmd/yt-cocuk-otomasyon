# 🤖 YouTube Niş Video Otomasyonu — GitHub Actions (Otonom)

Bu depo, **filigransız** video üreten ve YouTube'a yükleyen tam otomatik bir sistemdir.
Artık **Make'e gerek yok** — her şey GitHub Actions içinde, zamanlanmış olarak kendi kendine çalışır.
(Eski Make/dispatch yolu hâlâ opsiyonel olarak duruyor, bkz. aşağıda.)

## Nasıl çalışıyor?

İki bağımsız otonom hat vardır:

```
KISA (dikey / Shorts)  —  .github/workflows/otomasyon.yml   (her gün 17:00 UTC)
   └─ senaryolar.json'dan sıradaki hazır senaryo
        └─ TTS (edge-tts / Google TTS) + Pexels stok video + FFmpeg + altyazı
             └─ kapak.py ile çarpıcı kapak
                  └─ YouTube'a zamanlanmış yükleme (16:00 UTC'de public olur)

UZUN (yatay ~6 dk)     —  .github/workflows/uzun.yml         (her gün 08:00 UTC)
   └─ uzun_script.py: senaryo üretir
        · Anthropic Claude (birincil, en kaliteli Türkçe)
        · Gemini (yedek) → Pollinations (son çare)
        └─ ElevenLabs gerçekçi ses + Pexels stok video + FFmpeg
             └─ kapak_uzun.py ile kapak
                  └─ YouTube'a yükler + ilgili short'a "detaylı video" yorumu bırakır
```

Video render'ı GitHub'da yapıldığı için **filigran yok, süre/boyut sınırı yok.**
Kısa hat, çalışma anında AI'ya bağımlı değildir (senaryolar `senaryolar.json`'da hazırdır) → dayanıklıdır.

---

## KURULUM (tek seferlik)

### 1) Bu depoyu GitHub'a yükle
Yeni bir GitHub reposu aç, bu klasördeki tüm dosyaları içine at.

### 2) YouTube yükleme izni
1. https://console.cloud.google.com → yeni proje → **"YouTube Data API v3"**ü etkinleştir.
2. **OAuth consent screen** doldur.
   > ⚠️ **Önemli:** Yayın durumunu **"Production" (Yayında)** yap. "Testing" modunda kalırsa
   > refresh token **7 günde bir geçersiz olur** (`invalid_grant: Token expired or revoked`).
3. Credentials → OAuth client ID → **Desktop app** → `client_secret.json` indir.
4. Kendi bilgisayarında:
   ```bash
   pip install google-auth-oauthlib
   python3 token_al.py
   ```
   Çıkan **YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN** değerlerini kopyala.

### 3) GitHub Secrets
Repo → **Settings → Secrets and variables → Actions → New repository secret**.

**Zorunlu (YouTube yükleme):**
| Secret | Açıklama |
|--------|----------|
| `YT_CLIENT_ID` | OAuth istemci kimliği |
| `YT_CLIENT_SECRET` | OAuth istemci sırrı |
| `YT_REFRESH_TOKEN` | `token_al.py`'den gelen refresh token |

**Senaryo üretimi (uzun hat için; kısa hat hazır senaryo kullanır):**
| Secret | Açıklama |
|--------|----------|
| `CLAUDE_API_KEY` | Anthropic Claude anahtarı (birincil sağlayıcı). `ANTHROPIC_API_KEY` de kabul edilir. |
| `ANTHROPIC_MODEL` | *(opsiyonel)* Model seçimi, örn. `claude-sonnet-5` (maliyet için). Boşsa varsayılan kullanılır. |
| `GEMINI_API_KEY` / `GEMINI_KEY` / `GEMINI_KEY_UZUN` | Gemini yedek anahtar(lar)ı. `GEMINI_KEY_UZUN` uzun hatta ayrı kota için. |

**Ses ve görsel:**
| Secret | Açıklama |
|--------|----------|
| `ELEVENLABS_API_KEY` | Gerçekçi ses (uzun videolar). |
| `ELEVEN_VOICE_ID` | Kullanılacak ElevenLabs ses kimliği. |
| `GOOGLE_TTS_KEY` | *(opsiyonel)* Google TTS anahtarı. Yoksa ücretsiz edge-tts kullanılır. |
| `PEXELS_API_KEY` | Gerçek stok video için (ücretsiz Pexels API). |

### 4) Test
- Repo → **Actions** sekmesi → **"Gunluk Bilim Videosu"** (kısa) veya **"Uzun Video (Otonom)"** →
  **Run workflow** ile elle tetikle.
- İş çalışır, video üretilir ve YouTube'a yüklenir. İlk hafta `config.json`'da `"gizlilik": "private"` kalsın.

Bundan sonra iki hat da **zamanlanmış cron** ile her gün kendiliğinden çalışır (workflow dosyalarındaki `schedule`).

---

## AYARLAR — `config.json`

```json
{
  "format": "dikey",
  "ses": "erkek",
  "tonlama": "+0Hz",
  "gizlilik": "public",
  "kategori": "28",
  "cocuk_icerigi": false,
  "animasyon": true,
  "hiz": "+6%",
  "yayin_saati_utc": "16:00",
  "gorsel_stil": "stok",
  "uzun_gizlilik": "private",
  "uzun_gorsel_stil": "stok"
}
```

| Anahtar | Anlamı |
|---------|--------|
| `format` | `dikey` (Shorts) \| `yatay` |
| `ses` | `erkek` \| `kadin` |
| `hiz` / `tonlama` | Seslendirme hızı (`+6%`) ve ton (`+0Hz`) |
| `gizlilik` | Kısa video: `private` \| `unlisted` \| `public` |
| `kategori` | 27=Eğitim, 28=Bilim, 24=Eğlence, 22=Blog |
| `cocuk_icerigi` | "Made for Kids" işaretlemesi |
| `yayin_saati_utc` | Kısa videonun zamanlanmış yayın saati (UTC) |
| `gorsel_stil` / `uzun_gorsel_stil` | `stok` (Pexels) vb. |
| `uzun_gizlilik` | Uzun video: `private` (zamanlanmış) \| `unlisted` \| `public` |

### Konu havuzu
- **Kısa hat:** `senaryolar.json` içindeki hazır senaryolardan sırayla ilerler; ilerleme `durum.json`'da tutulur.
- **Uzun hat:** işlenen konuyu `uzun_scripts/<slug>.json` altında manuel script varsa ondan, yoksa AI ile üretir; durum `uzun_durum.json`'da tutulur.
- Yeni konu eklemek için `senaryolar.json`'a giriş ekle veya `basliklar.txt`'yi kullan.

---

## OPSİYONEL — Make / Dış Tetikleme

Dilersen dışarıdan (Make, cron servisi, kendi scriptin) tetikleyebilirsin:
`.github/workflows/uret.yml`, `repository_dispatch` (tip: `uret`) ve manuel `workflow_dispatch` destekler.
Bu yol için ek olarak GitHub Personal Access Token (scope: **repo**) ile şu isteği atman yeterli:
```
POST https://api.github.com/repos/KULLANICI/REPO/dispatches
Authorization: Bearer <GITHUB_PAT>
{ "event_type": "uret", "client_payload": { "b64": "<base64 senaryo JSON>" } }
```

---

## GÖRSELLER
Varsayılan: Pexels'ten konuya uygun **gerçek stok videolar**. Alternatif olarak metinden
otomatik degrade başlık kartı üretilebilir. `assets/` klasörüne telifsiz `.jpg/.png` koyarsan
Ken Burns zoom ile kullanılır.

---

## DAYANIKLILIK
Sistem hatalara karşı sağlamlaştırılmıştır (ayrıntı: `RESILIENCE_GUIDE.md`):
- AI senaryo üretiminde çok katmanlı yedekleme (Claude → Gemini → Pollinations).
- Türkçe karakter doğrulaması (diakritiksiz/ASCII üretimi reddedilir).
- Kısa video public olmadan yönlendirme yorumu atılmaz (403 önlenir), yayına girince atılır.
- Başarılı çalışmada eski `hata.log` otomatik temizlenir.

## GÜVENLİK
Tüm anahtarları **yalnızca GitHub Secrets**'a gir; düz metin olarak repoya koyma.
`client_secret.json`'u repoya **yükleme**.
