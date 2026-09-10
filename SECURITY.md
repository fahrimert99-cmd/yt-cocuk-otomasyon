# Güvenlik Politikası

## Güvenlik Açığı Bildirimi

Bu projede bir güvenlik açığı veya sızmış bir gizli anahtar (secret) fark ederseniz,
lütfen **herkese açık bir issue açmayın**. Bunun yerine durumu doğrudan proje
sahibine bildirin:

- **E-posta:** fahrimert99@gmail.com

Bildiriminizde şunları paylaşmanız incelemeyi hızlandırır:

- Açığın kısa açıklaması ve etkisi
- Yeniden üretmek için adımlar (varsa)
- İlgili dosya/işlev veya workflow adı

Bildirimlerinize makul bir süre içinde dönüş yapılacaktır.

## Gizli Anahtarların (Secrets) Yönetimi

Bu proje aşağıdaki servislerin anahtarlarını kullanır ve bunların tamamı
**GitHub Actions Secrets** üzerinden sağlanır — hiçbir anahtar depoya
yazılmamalıdır:

- YouTube Data API
- Anthropic Claude / Google Gemini
- ElevenLabs
- Pexels / Pixabay
- NVIDIA

### Uyulması gereken kurallar

- `client_secret.json` ve benzeri kimlik dosyaları **asla** commit edilmez
  (bunlar `.gitignore` ile engellenmiştir).
- Bir anahtarın yanlışlıkla depoya girdiğini fark ederseniz, o anahtarı
  ilgili serviste **derhal iptal edip yenileyin** — geçmişten silmek tek
  başına yeterli değildir, çünkü anahtar zaten ifşa olmuştur.
- Yeni bir servis eklerken anahtarını yalnızca GitHub Secrets'a ekleyin ve
  workflow içinde `${{ secrets.ANAHTAR_ADI }}` olarak kullanın.

## Desteklenen Sürümler

Bu proje sürekli geliştirilen bir otomasyon deposudur; güvenlik düzeltmeleri
her zaman `main` dalı üzerinde uygulanır.
