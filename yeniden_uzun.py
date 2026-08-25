#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tek seferlik: PLANLI (private + publishAt) bir UZUN (gizem) videoyu, ses
cizirtisi duzeltmesiyle YENIDEN uretir; ESKI videonun basligini, aciklamasini,
etiketlerini ve ZAMANLANMIS yayin saatini KORUR, eskisini siler.

Neden: video.py'deki ses duzeltmesi (clipping limiter + gapless concat) yalniz
bundan SONRA uretilen videolara uygulanir. Zaten yuklenmis planli videoyu temiz
sesle degistirmek icin bu betik kullanilir.

Uzun (Shorts) gunluk akisina DOKUNMAZ; sadece verilen video_id'yi degistirir.
uzun_durum.json'daki "yapilan_id"/"son" kaydini yeni id ile gunceller.

Ortam degiskenleri (GitHub Secrets + workflow input):
  KONU            Yeniden uretilecek uzun konu basligi (uzun_konular.json'daki)
  ESKI_VIDEO_ID   Degistirilecek (silinecek) mevcut YouTube video id'si  [ZORUNLU]
  ELEVENLABS_API_KEY / ELEVEN_VOICE_ID / YT_* / GEMINI_API_KEY / CLAUDE(*)
Ayarlar: config.json
"""
import os, json, tempfile, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
import video as V
import youtube_yukle as YT
import uzun_script

CFG_P = "config.json"; UZUN_P = "uzun_durum.json"


def _load(p, d):
    try:
        with open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return d


def _eleven_kredi_yeter(gereken_karakter):
    key = V._eleven_key()
    if not key:
        raise SystemExit("ElevenLabs anahtari yok — secret ELEVENLABS_API_KEY eksik.")
    req = urllib.request.Request("https://api.elevenlabs.io/v1/user/subscription",
                                 headers={"xi-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as he:
        raise SystemExit(f"ElevenLabs kredi sorgusu basarisiz: {he.code} {he.read().decode()[:200]}")
    kalan = int(d.get("character_limit", 0)) - int(d.get("character_count", 0))
    print(f"      [ElevenLabs kalan kredi: {kalan} karakter, gereken ~{gereken_karakter}]")
    return kalan >= gereken_karakter


def _eski_meta(video_id):
    """Eski videonun snippet + status'unu getirir; boylece BASLIK/ACIKLAMA/
    ETIKET/KATEGORI ve ZAMANLANMIS yayin saati (publishAt) korunur."""
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", credentials=YT._kimlik())
    r = yt.videos().list(part="snippet,status", id=video_id).execute()
    items = r.get("items", [])
    if not items:
        return None
    sn = items[0].get("snippet", {}); stt = items[0].get("status", {})
    return {
        "baslik": sn.get("title", ""),
        "aciklama": sn.get("description", ""),
        "etiketler": sn.get("tags", []),
        "kategori": sn.get("categoryId", "27"),
        "publishAt": stt.get("publishAt"),   # None ise zamanlanmis degil
    }


def main():
    konu = (os.environ.get("KONU", "").strip())
    eski_id = os.environ.get("ESKI_VIDEO_ID", "").strip()
    if not konu:
        raise SystemExit("KONU verilmedi (uzun_konular.json'daki birebir baslik).")
    if not eski_id:
        raise SystemExit("ESKI_VIDEO_ID verilmedi — degistirilecek video belli degil.")

    cfg = _load(CFG_P, {})

    # --- Eski videonun kimligini (baslik/aciklama/etiket/kategori/yayin saati) al ---
    meta = _eski_meta(eski_id)
    if not meta:
        raise SystemExit(f"Eski video bulunamadi: {eski_id} — id yanlis ya da silinmis.")
    yayin = meta.get("publishAt")
    if yayin:
        # Zaten gecmisse (yayina cikmissa) yeniden planlama; bir sonraki 18:00 UTC'ye al.
        try:
            pt = datetime.fromisoformat(yayin.replace("Z", "+00:00"))
            if pt <= datetime.now(timezone.utc) + timedelta(minutes=10):
                yayin = None
        except Exception:
            pass
    if not yayin:
        h = datetime.now(timezone.utc).replace(hour=18, minute=0, second=0, microsecond=0)
        if h <= datetime.now(timezone.utc) + timedelta(minutes=10):
            h += timedelta(days=1)
        yayin = h.isoformat().replace("+00:00", "Z")
    print(f"[1/5] Konu: {konu!r}\n      Baslik(korunan): {meta['baslik']!r}\n      Yayin(korunan): {yayin}")

    # --- Script uret (elle override varsa onu kullan) ---
    import re as _re, unicodedata as _ud
    def _slug(t):
        t = _ud.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
        return _re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    _man = os.path.join("uzun_scripts", _slug(konu) + ".json")
    if os.path.exists(_man):
        with open(_man, encoding="utf-8-sig") as _f:
            uzun = json.load(_f)
        print("      [manuel script kullanildi]", _man)
    else:
        uzun = uzun_script.uret(konu)
    script = (uzun.get("script") or "").strip()
    if not script:
        raise SystemExit("Script bos uretildi.")

    # --- GUVENLIK: ElevenLabs kredisi gercekten var mi? Yoksa eskiyi SILME ---
    if not _eleven_kredi_yeter(max(600, len(script) * 2)):
        raise SystemExit("ElevenLabs kredisi yetersiz — eski video KORUNDU, yeni video uretilmedi.")

    tmp = tempfile.mkdtemp(); sp = os.path.join(tmp, "script.txt")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(script)
    os.makedirs("output", exist_ok=True); cikti = "output/uzun_video.mp4"
    print("[2/5] Yatay render (ElevenLabs, ses duzeltmeli) ...")
    V.uret_video(sp, cikti, ses=cfg.get("ses", "erkek"), dikey=False,
                 hiz=str(cfg.get("uzun_hiz", cfg.get("hiz", "+5%"))),
                 sahneler=uzun.get("sahneler"), animasyon=bool(cfg.get("animasyon", True)),
                 cocuk=bool(cfg.get("cocuk_icerigi", False)), tonlama=str(cfg.get("tonlama", "+0Hz")),
                 gorsel_stil=str(cfg.get("uzun_gorsel_stil", "stok")),
                 kanca=(uzun.get("kanca") or meta["baslik"] or konu),
                 eleven_once=True)
    print(f"      Cikti: {cikti}  ({os.path.getsize(cikti)//1024} KB)")

    kapak = None
    try:
        import kapak_uzun as K
        kapak = K.kapak_uret(cikti, meta["baslik"], "output/uzun_kapak.jpg", kanca=uzun.get("kanca"))
        print(f"      Kapak: {kapak}")
    except Exception as e:
        print("      kapak atlandi:", str(e)[:80])

    print("[3/5] Yeni video yukleniyor (planli, eski kimlikle) ...")
    yeni_id = YT.yukle(cikti, meta["baslik"], meta["aciklama"], meta["etiketler"],
                       gizlilik="private", kategori=str(meta.get("kategori", "27")),
                       cocuk_icerigi=bool(cfg.get("cocuk_icerigi", False)),
                       kapak=kapak, yayin_zamani=yayin)
    yeni_url = f"https://youtu.be/{yeni_id}"

    print("[4/5] Eski (cizirtili) video siliniyor ...")
    try:
        YT.sil(eski_id)
    except Exception as e:
        print(f"! Eski video silinemedi ({str(e)[:140]}). Yeni yuklendi: {yeni_url}. Eskiyi elle sil: {eski_id}")

    print("[5/5] uzun_durum.json guncelleniyor ...")
    u = _load(UZUN_P, {})
    ids = u.get("yapilan_id", [])
    u["yapilan_id"] = [yeni_id if x == eski_id else x for x in ids]
    if eski_id not in ids:
        u["yapilan_id"] = ids + [yeni_id]
    if isinstance(u.get("son"), dict) and u["son"].get("uzun_url", "").endswith(eski_id):
        u["son"]["uzun_url"] = yeni_url
    with open(UZUN_P, "w", encoding="utf-8") as f:
        json.dump(u, f, ensure_ascii=False, indent=2)

    print(f"TAMAM ✓  Temiz sesli yeni video: {yeni_url}  (yayin: {yayin} UTC)")


if __name__ == "__main__":
    main()
