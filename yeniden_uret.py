#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tek seferlik: senaryolar.json'daki BELİRLİ bir başlığı ElevenLabs sesiyle
YENİDEN üretir, aynı yayın saatine planlar ve eski (yedek sesli) videoyu siler.

Kullanım amacı: ElevenLabs kredisi bitince günlük cron videoyu Google TTS ile
üretip yükler. Kredi tekrar yüklenince bu betik o videoyu ElevenLabs sesiyle
yeniden üretip değiştirir. Günlük akışa (otomasyon.py / durum.json) DOKUNMAZ.

Ortam değişkenleri:
  BASLIK          Yeniden üretilecek senaryonun başlığı (senaryolar.json'daki birebir)
  ESKI_VIDEO_ID   Silinecek eski YouTube video id'si (bos ise silme atlanir)
  YAYIN_ZAMANI    Planlı yayın (UTC, örn 2026-08-17T16:00:00Z; bos ise config.gizlilik)
  ELEVENLABS_API_KEY / ELEVEN_VOICE_ID / YT_* (GitHub Secrets)
Ayarlar: config.json
"""
import os, json, tempfile, urllib.request, urllib.error
import video as V

VARSAYILAN_BASLIK = "OYUNCAK NEDEN KASADA? 🧸"


def _senaryo_bul(baslik):
    with open("senaryolar.json", encoding="utf-8-sig") as f:
        senaryolar = json.load(f)
    for s in senaryolar:
        if s.get("baslik", "").strip() == baslik.strip():
            return s
    raise SystemExit(f"Senaryo bulunamadi: {baslik!r} (senaryolar.json)")


def _eleven_kredi_yeter(gereken_karakter):
    """ElevenLabs aboneligini sorgula; yeterli kredi yoksa False don.
    Boylece kredi hala yoksa ESKI VIDEO SILINMEZ / yeni video yuklenmez."""
    key = V._eleven_key()
    if not key:
        raise SystemExit("ElevenLabs anahtari yok — secret ELEVENLABS_API_KEY eksik.")
    req = urllib.request.Request(
        "https://api.elevenlabs.io/v1/user/subscription",
        headers={"xi-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as he:
        raise SystemExit(f"ElevenLabs kredi sorgusu basarisiz: {he.code} {he.read().decode()[:200]}")
    kalan = int(d.get("character_limit", 0)) - int(d.get("character_count", 0))
    print(f"      [ElevenLabs kalan kredi: {kalan} karakter, gereken ~{gereken_karakter}]")
    return kalan >= gereken_karakter


def _eski_durum(video_id):
    """Eski videonun privacyStatus + publishAt bilgisini getirir; boylece
    zamanlanmis yayin saati KORUNUR ya da zaten public ise yeni video da hemen
    public yuklenir. Hata/bulunamama -> None."""
    try:
        from googleapiclient.discovery import build
        import youtube_yukle as YT
        yt = build("youtube", "v3", credentials=YT._kimlik())
        r = yt.videos().list(part="status", id=video_id).execute()
        items = r.get("items", [])
        if not items:
            return None
        st = items[0].get("status", {})
        return {"privacy": st.get("privacyStatus"), "publishAt": st.get("publishAt")}
    except Exception as e:
        print(f"      [eski video durumu okunamadi: {str(e)[:100]}]")
        return None


def main():
    from datetime import datetime, timezone, timedelta
    baslik = (os.environ.get("BASLIK", "").strip() or VARSAYILAN_BASLIK)
    eski_id = os.environ.get("ESKI_VIDEO_ID", "").strip()
    yayin_zamani = os.environ.get("YAYIN_ZAMANI", "").strip() or None

    with open("config.json", encoding="utf-8-sig") as f:
        cfg = json.load(f)

    # --- Yayin saati/gizliligi eski videoyla ESLE (YAYIN_ZAMANI verilmediyse) ---
    gizlilik = cfg.get("gizlilik", "public")
    if not yayin_zamani and eski_id:
        durum = _eski_durum(eski_id)
        if durum:
            pa = durum.get("publishAt")
            if pa:  # zamanlanmis: ayni saati koru (gecmisse hemen public'e dus)
                try:
                    pt = datetime.fromisoformat(pa.replace("Z", "+00:00"))
                    if pt > datetime.now(timezone.utc) + timedelta(minutes=10):
                        yayin_zamani = pa
                        print(f"      [zamanlanmis yayin korunuyor: {pa}]")
                    else:
                        gizlilik = "public"
                except Exception:
                    yayin_zamani = pa
            elif durum.get("privacy") == "public":
                gizlilik = "public"; print("      [eski video public -> yeni video da hemen public]")
            elif durum.get("privacy"):
                gizlilik = durum["privacy"]

    veri = _senaryo_bul(baslik)
    script = (veri.get("script") or "").strip()
    if not script:
        raise SystemExit(f"Senaryonun script'i bos: {baslik!r}")
    print(f"[1/4] Senaryo: {baslik}  ({len(script.split())} kelime)")

    # --- GUVENLIK: once ElevenLabs kredisi gercekten var mi? Yoksa hicbir sey silme/yukleme ---
    if not _eleven_kredi_yeter(max(300, len(script) * 2)):
        raise SystemExit("ElevenLabs kredisi hala yetersiz — eski video KORUNDU, yeni video "
                         "uretilmedi. Kredi yukleyip tekrar dene.")

    dikey = str(cfg.get("format", "dikey")).lower() == "dikey"
    tmp = tempfile.mkdtemp()
    sp = os.path.join(tmp, "script.txt")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(script)
    os.makedirs("output", exist_ok=True)
    cikti = "output/video.mp4"
    print("[2/4] Video ElevenLabs sesiyle uretiliyor ...")
    V.uret_video(sp, cikti,
                 ses=cfg.get("ses", "erkek"),
                 dikey=dikey,
                 hiz=str(cfg.get("hiz", "+15%")),
                 sahneler=veri.get("sahneler"),
                 animasyon=bool(cfg.get("animasyon", True)),
                 cocuk=bool(cfg.get("cocuk_icerigi", False)),
                 tonlama=str(cfg.get("tonlama", "+0Hz")),
                 gorsel_stil=str(cfg.get("gorsel_stil", "stok")),
                 kanca=veri.get("kanca"),
                 eleven_once=True,  # bu betikte HER ZAMAN ElevenLabs oncelikli
                 eleven_voice_id=str(cfg.get("kisa_ses_id", "")).strip() or None)
    print(f"      Cikti: {cikti}  ({os.path.getsize(cikti)//1024} KB)")

    kapak_yolu = None
    try:
        import kapak as K
        kapak_yolu = K.kapak_uret(cikti, baslik, "output/kapak.jpg")
        print(f"      Kapak: {kapak_yolu}")
    except Exception as e:
        print(f"      Kapak uretilemedi: {str(e)[:120]}")

    print("[3/4] Yeni video YouTube'a yukleniyor ...")
    import youtube_yukle as YT
    yeni_id = YT.yukle(cikti, baslik, veri.get("aciklama", ""),
                       veri.get("etiketler", []),
                       gizlilik=gizlilik,
                       kategori=str(cfg.get("kategori", "28")),
                       cocuk_icerigi=bool(cfg.get("cocuk_icerigi", False)),
                       kapak=kapak_yolu, yayin_zamani=yayin_zamani)

    # [4/4] Yeni video basariyla yuklendikten SONRA eskiyi sil (sirasi onemli:
    # yukleme patlarsa eski video kaybolmaz).
    if eski_id:
        print("[4/4] Eski (yedek sesli) video siliniyor ...")
        try:
            YT.sil(eski_id)
        except Exception as e:
            print(f"! Eski video silinemedi ({str(e)[:160]}). Yeni video yuklendi: {yeni_id}. "
                  f"Eskiyi elle silebilirsin: {eski_id}")
    else:
        print("[4/4] ESKI_VIDEO_ID verilmedi — silme atlandi.")

    # durum.json'daki eski id referanslarini yeni id ile guncelle (bekleyen yorum
    # yeni videoya dussun, yapilan_id tutarli kalsin). durum.json'a baska dokunma.
    if eski_id and yeni_id:
        try:
            with open("durum.json", encoding="utf-8-sig") as f:
                d = json.load(f)
            degisti = False
            if isinstance(d.get("yapilan_id"), list) and eski_id in d["yapilan_id"]:
                d["yapilan_id"] = [yeni_id if x == eski_id else x for x in d["yapilan_id"]]
                degisti = True
            by = d.get("bekleyen_yorum")
            if isinstance(by, dict) and by.get("video_id") == eski_id:
                by["video_id"] = yeni_id; degisti = True
            if isinstance(d.get("son_video"), dict) and d["son_video"].get("id") == eski_id:
                d["son_video"]["id"] = yeni_id; degisti = True
            if degisti:
                with open("durum.json", "w", encoding="utf-8") as f:
                    json.dump(d, f, ensure_ascii=False, indent=2)
                print("      [durum.json guncellendi: eski id -> yeni id]")
        except Exception as e:
            print(f"      [durum.json guncellenemedi: {str(e)[:100]}]")

    print(f"TAMAM ✓  Yeni ElevenLabs'li video: https://youtu.be/{yeni_id}"
          + (f"  (yayin: {yayin_zamani} UTC)" if yayin_zamani else ""))


if __name__ == "__main__":
    main()
