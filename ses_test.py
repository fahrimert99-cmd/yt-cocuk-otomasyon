#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SES A/B TESTİ (YÜKLEMEZ). Aynı Türkçe cümleyi MEVCUT ses + birkaç farklı temiz
ElevenLabs sesiyle (de-esser'lı) üretir ve TEK karşılaştırma videosu yapar; her
segmentin başında büyük bir etiket kartı olur. Kullanıcı hangisinin cızırtısız
olduğunu duyunca, cızırtının SESTEN mi yoksa pipeline'dan mı geldiği netleşir.

Env: ELEVENLABS_API_KEY (zorunlu), ELEVEN_VOICE_ID (opsiyonel; config.kisa_ses_id
öncelikli). YouTube secret'ı yok -> kanala DOKUNMAZ.
"""
import os, json, subprocess
import video as V

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
# Sibilance (s/ş/z) yoğun cümle -> cızırtı en belirgin burada duyulur.
METIN = ("Süpermarketlerde şaşırtıcı bir gerçek var. Fiyatlar neden hep dokuz "
         "ile bitiyor? Sessizce cebinizden çıkan bu parayı çoğu insan hiç fark etmiyor.")


def _cfg_ses():
    try:
        with open("config.json", encoding="utf-8-sig") as f:
            return str(json.load(f).get("kisa_ses_id", "")).strip()
    except Exception:
        return ""


def _seg(ad, voice_id, tmp, idx, deess=True, saglayici="eleven"):
    mp3 = os.path.join(tmp, f"v{idx}.mp3")
    try:
        if saglayici == "openai":
            V._openai_seslendir(METIN, mp3, voice_id=voice_id or None)
        else:
            V._eleven_seslendir(METIN, mp3, voice_id=voice_id or None)
    except Exception as e:
        print(f"  ! {ad}: TTS hata {str(e)[:120]}")
        return None
    ses = V._ses_temizle(mp3, tmp) if deess else mp3
    try:
        dur = V.sure_al(ses)
    except Exception:
        dur = 8.0
    seg = os.path.join(tmp, f"seg{idx}.mp4")
    label = ad.replace(":", " ").replace("'", "")
    vf = (f"drawtext=fontfile={FONT}:text='{label}':fontcolor=white:fontsize=40:"
          f"x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.55:boxborderw=24")
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x0e1116:s=720x480:d={dur:.2f}",
           "-i", ses, "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
           "-shortest", seg]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0 and os.path.exists(seg) and os.path.getsize(seg) > 5000:
        print(f"  ✓ {ad} ({dur:.1f}s)")
        return seg
    print(f"  ! {ad}: ffmpeg hata {(r.stderr or '')[-160:]}")
    return None


def main():
    os.makedirs("output", exist_ok=True)
    tmp = "output/_sestest"
    os.makedirs(tmp, exist_ok=True)
    mevcut = _cfg_ses() or os.environ.get("ELEVEN_VOICE_ID", "").strip()
    print(f"Mevcut ses id: {mevcut or '(varsayılan)'}")
    # (etiket, voice_id, de-esser?, saglayici) — MEVCUT ElevenLabs vs OpenAI TTS
    # karşılaştırması (Türkçe). OpenAI sesleri: onyx/ash/ballad/sage/echo...
    testler = [
        ("1 - MEVCUT (ElevenLabs Bill)", mevcut or "pqHfZKP75CvOlQylNhV4", True, "eleven"),
        ("2 - OpenAI ONYX",              "onyx",                            True, "openai"),
        ("3 - OpenAI ASH",               "ash",                             True, "openai"),
        ("4 - OpenAI BALLAD",            "ballad",                          True, "openai"),
        ("5 - OpenAI SAGE",              "sage",                            True, "openai"),
        ("6 - OpenAI ECHO",              "echo",                            True, "openai"),
    ]
    segs = []
    for i, (ad, vid, de, sag) in enumerate(testler):
        s = _seg(ad, vid, tmp, i, deess=de, saglayici=sag)
        if s:
            segs.append(s)
    if not segs:
        raise SystemExit("Hiç segment üretilemedi (ElevenLabs anahtarı?).")
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for s in segs:
            f.write(f"file '{os.path.abspath(s)}'\n")
    out = "output/ses_test.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "44100", out],
                   check=True, capture_output=True)
    print(f"TAMAM ✓  {out}  ({os.path.getsize(out)//1024} KB, {len(segs)} segment)")


if __name__ == "__main__":
    main()
