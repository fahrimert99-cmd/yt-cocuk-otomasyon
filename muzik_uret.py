#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ElevenLabs Music API ile arka fon müziği SETİ üretir — TEK SEFERLİK.

Üretilen parçalar assets/muzik/<tema>.mp3 olarak kaydedilir. Pipeline bunları
YEREL kaynak olarak kullanır (video.py._muzik_yerel_sec), böylece HER VİDEODA
yeniden üretim OLMAZ -> ElevenLabs kredisi korunur. Bir daha çalıştırılırsa
parçalar yenilenir (üzerine yazılır).

Ortam:
  ELEVENLABS_API_KEY  (GitHub Secret) — zorunlu
  MUZIK_SN            saniye cinsinden parça uzunluğu (varsayılan 45)

Music API planda kapalıysa/erişilemiyorsa betik HATA verir; o durumda pipeline
config.arka_muzik_kaynaklar'daki FreePD (CC0) yedeğini kullanmaya devam eder.
"""
import os, json, base64, urllib.request, urllib.error

ENDPOINT = "https://api.elevenlabs.io/v1/music"

# (dosya adı = tema anahtarı, prompt). video.py tema eşleşmesi:
#   genel*  -> kısa videolar (genel + genel2 rastgele),  merak* -> merak,  haber* -> haber
SET = [
    ("genel", "Minimal, subtly tense cinematic underscore for a consumer-warning short video. "
              "Low pulsing bass, soft sustained strings, mysterious and modern, steady, no big "
              "drops or drum buildups, fully instrumental and understated so a voiceover sits on "
              "top. Loopable."),
    ("genel2", "Curious investigative background score. Light plucked pizzicato strings, a gentle "
               "ticking pulse, intriguing and clean, modern documentary feel, steady low intensity, "
               "instrumental, leaves space for narration. Loopable."),
    ("merak", "Mysterious, slightly suspenseful ambient underscore. Warm low pads, subtle tension, "
              "unhurried, cinematic and elegant, no percussion spikes, instrumental and soft enough "
              "for a voice on top. Loopable."),
    ("haber", "Serious, neutral news underscore. Understated corporate-cinematic bed, steady soft "
              "pulse, professional and calm but alert, instrumental, designed to sit under a news "
              "voiceover. Loopable."),
]


def _iste(body):
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY yok.")
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(body).encode(),
        headers={"xi-api-key": key, "Content-Type": "application/json",
                 "Accept": "audio/mpeg"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def _kaydet(data, out):
    # Ham mp3 (ID3 ya da MPEG frame) doğrudan; JSON+base64 gelirse çöz.
    if data[:3] == b"ID3" or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        with open(out, "wb") as f:
            f.write(data)
        return True
    try:
        d = json.loads(data.decode())
        b64 = d.get("audio_base64") or (d.get("audio") or {}).get("base64")
        if not b64:
            raise ValueError("yanıtta audio yok: " + str(d)[:200])
        with open(out, "wb") as f:
            f.write(base64.b64decode(b64))
        return True
    except Exception as e:
        raise RuntimeError("beklenmeyen yanıt: " + str(e)[:200])


def uret_bir(tema, prompt, sure_ms):
    out = os.path.join("assets", "muzik", f"{tema}.mp3")
    # Gövde varyantları: minimal -> model_id'li (API sürüm farkına dayanıklı).
    denemeler = [
        {"prompt": prompt, "music_length_ms": sure_ms},
        {"prompt": prompt, "music_length_ms": sure_ms, "model_id": "music_v1"},
    ]
    son_hata = ""
    for body in denemeler:
        try:
            data = _iste(body)
            _kaydet(data, out)
            return out
        except urllib.error.HTTPError as he:
            son_hata = f"HTTP {he.code}: {he.read().decode()[:300]}"
        except Exception as e:
            son_hata = str(e)[:300]
    raise RuntimeError(son_hata or "bilinmeyen hata")


def main():
    os.makedirs(os.path.join("assets", "muzik"), exist_ok=True)
    _sn = (os.environ.get("MUZIK_SN") or "").strip() or "45"  # boş girdi -> 45
    try:
        sure_ms = int(float(_sn) * 1000)
    except ValueError:
        sure_ms = 45000
    sure_ms = max(10000, min(180000, sure_ms))
    ok = 0
    for tema, prompt in SET:
        try:
            out = uret_bir(tema, prompt, sure_ms)
            print(f"✓ {tema}: {out} ({os.path.getsize(out)//1024} KB)")
            ok += 1
        except Exception as e:
            print(f"✗ {tema}: {str(e)[:300]}")
    print(f"TAMAM: {ok}/{len(SET)} parça üretildi.")
    if ok == 0:
        raise SystemExit("Hiç parça üretilemedi — ElevenLabs Music API planda "
                         "kapalı/erişilemez olabilir. Pipeline FreePD (CC0) "
                         "yedeğiyle devam eder.")


if __name__ == "__main__":
    main()
