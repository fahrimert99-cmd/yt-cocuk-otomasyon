#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Xiaomi MiMo API DENEME raporu (YÜKLEMEZ, kanala ve senaryolar.json'a DOKUNMAZ).

Amaç: MiMo'nun bu kanalda nerede işe yarayacağını gerçek çıktılarla görmek.
  1) GET /v1/models            -> hesabın erişebildiği modeller
  2) Model seçimi              -> ilk cevap veren sohbet modeli
  3) SENARYO                   -> senaryolar.json formatında örnek kısa senaryo (JSON)
  4) SEO                       -> mevcut bir senaryo için alternatif başlık/kanca
  5) GÖRSEL ANLAMA (kapak)     -> assets/marka/banner.png'yi değerlendirir
  6) VİDEO ANLAMA (kalite)     -> ffmpeg ile üretilen kısa test klibini izletir

Çıktılar yalnızca output/ altına yazılır:
  output/mimo_rapor.txt, output/mimo_modeller.txt, output/mimo_ornek_senaryo.json

Env: MIMO_API_KEY (zorunlu), MIMO_BASE_URL (ops.), MIMO_MODEL (ops.).
Özet EN SONA basılır (log aracı yalnızca sonu döndürüyor).
"""
import os, re, io, json, base64, shutil, subprocess, tempfile, time
import urllib.request, urllib.error

KEY = re.sub(r"\s", "", os.environ.get("MIMO_API_KEY") or "")
BASE = (os.environ.get("MIMO_BASE_URL") or "https://api.xiaomimimo.com/v1").rstrip("/")
OZET = []
def _o(m): OZET.append(str(m)); print(m)


def _headers():
    # Dokümanda Bearer; bazı örneklerde 'api-key' başlığı. İkisi birden zararsız.
    return {"Authorization": f"Bearer {KEY}", "api-key": KEY,
            "Content-Type": "application/json", "Accept": "application/json"}


def _istek(yol, body=None, timeout=60):
    url = f"{BASE}{yol}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=_headers(),
                                 method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _hata(e):
    if isinstance(e, urllib.error.HTTPError):
        try:
            det = e.read().decode()[:200]
        except Exception:
            det = ""
        return f"HTTP {e.code} {det}"
    return f"{type(e).__name__}: {str(e)[:120]}"


def _sohbet(model, content, max_tokens=2048, timeout=120):
    """Tek mesajlık sohbet. (metin, süre_sn, token_kullanımı) döner."""
    t0 = time.time()
    d = _istek("/chat/completions", {
        "model": model, "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}]}, timeout=timeout)
    msg = (d.get("choices") or [{}])[0].get("message") or {}
    metin = (msg.get("content") or "").strip()
    return metin, round(time.time() - t0, 1), d.get("usage") or {}


def _json_ayikla(metin):
    metin = re.sub(r"^```(?:json)?|```$", "", metin.strip(), flags=re.M).strip()
    bas, son = metin.find("{"), metin.rfind("}")
    return json.loads(metin[bas:son + 1])


def _png_data_url(yol, en=768):
    from PIL import Image
    im = Image.open(yol).convert("RGB")
    im.thumbnail((en, en))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _test_klibi():
    """3 sn'lik küçük test videosu: ilk yarısı renkli desen, sonu SİYAH ekran.
    Model siyah kareyi fark ederse 'yükleme öncesi kalite kontrol' işe yarar."""
    if not shutil.which("ffmpeg"):
        return None
    yol = os.path.join(tempfile.mkdtemp(), "test.mp4")
    komut = ["ffmpeg", "-y", "-loglevel", "error",
             "-f", "lavfi", "-i", "testsrc=size=320x568:rate=10:duration=1.5",
             "-f", "lavfi", "-i", "color=c=black:size=320x568:rate=10:duration=1.5",
             "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]",
             "-pix_fmt", "yuv420p", "-c:v", "libx264", yol]
    try:
        subprocess.run(komut, check=True, timeout=60)
        return yol
    except Exception:
        return None


def main():
    print(f"MiMo anahtarı mevcut: {bool(KEY)} | base: {BASE}")
    if not KEY:
        _o("ANAHTAR YOK — MIMO_API_KEY secret'ı workflow'a verilmemiş.")
        return _yaz()
    os.makedirs("output", exist_ok=True)

    # 1) Modeller
    ids = []
    try:
        d = _istek("/models", timeout=30)
        ids = sorted(m.get("id", "") for m in d.get("data", []) if m.get("id"))
        with open("output/mimo_modeller.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(ids))
        _o(f"[1] /models: {len(ids)} model -> {', '.join(ids[:20]) or 'boş'}")
        ses = [i for i in ids if any(k in i.lower() for k in ("tts", "audio", "speech", "voice"))]
        vid = [i for i in ids if any(k in i.lower() for k in ("video", "vl", "omni"))]
        _o(f"    ses/tts adayları: {', '.join(ses) or 'YOK'} | video/vl adayları: {', '.join(vid) or 'YOK'}")
    except Exception as e:
        _o(f"[1] /models alınamadı: {_hata(e)}")

    # 2) Model seçimi: env > bilinen adaylar > listedekiler
    adaylar = [os.environ.get("MIMO_MODEL", "").strip(),
               "mimo-v2.6-flash", "mimo-v2.6-pro", "mimo-v2.5", "mimo-v2-flash"]
    adaylar += [i for i in ids if "mimo" in i.lower()]
    model, gorulen = None, set()
    for m in adaylar:
        if not m or m in gorulen:
            continue
        gorulen.add(m)
        try:
            cevap, sure, _ = _sohbet(m, "Sadece 'merhaba' yaz.", max_tokens=512, timeout=60)
            _o(f"[2] OK   {m} ({sure}s): {cevap[:40]!r}")
            model = model or m
        except Exception as e:
            _o(f"[2] HATA {m}: {_hata(e)}")
    if not model:
        _o("Çalışan model bulunamadı — anahtar/base URL/kota kontrol edilmeli.")
        return _yaz()
    _o(f"    Seçilen model: {model}")

    # 3) Senaryo üretimi (senaryolar.json formatında)
    ornek = json.load(open("senaryolar.json", encoding="utf-8"))[0]
    istem = (
        "Türkçe bir YouTube Shorts kanalı için senaryo yaz. Kanal konusu: tüketici "
        "tuzakları ve günlük hayattaki gizli hileler. Konu: 'Süpermarketlerde süt neden "
        "hep en arkadadır?'. Kısa, net, merak uyandıran, 35-45 saniyelik konuşma metni. "
        "Marka adı kullanma. SADECE geçerli JSON döndür, şu anahtarlarla: "
        "baslik, aciklama, etiketler (liste), script, kanca, sahneler (liste; her biri "
        "{metin, gorsel} — gorsel Pexels'te aranacak 2-4 kelimelik İNGİLİZCE ifade). "
        "Örnek format:\n" + json.dumps({k: ornek[k] for k in
            ("baslik", "aciklama", "etiketler", "script", "kanca")}, ensure_ascii=False)
        + ', "sahneler": [{"metin": "...", "gorsel": "..."}]')
    try:
        cevap, sure, kul = _sohbet(model, istem, max_tokens=4096, timeout=180)
        s = _json_ayikla(cevap)
        eksik = [k for k in ("baslik", "aciklama", "etiketler", "script", "kanca", "sahneler")
                 if k not in s]
        with open("output/mimo_ornek_senaryo.json", "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
        kelime = len(str(s.get("script", "")).split())
        _o(f"[3] SENARYO OK ({sure}s, token: {kul}) eksik alan: {eksik or 'yok'} | "
           f"script {kelime} kelime | {len(s.get('sahneler') or [])} sahne")
        _o(f"    başlık: {s.get('baslik')} | kanca: {s.get('kanca')}")
        _o(f"    script: {str(s.get('script'))[:400]}")
    except Exception as e:
        _o(f"[3] SENARYO HATA: {_hata(e)}")

    # 4) SEO: mevcut senaryoya alternatif başlık/kanca
    try:
        cevap, sure, _ = _sohbet(model,
            "Aşağıdaki YouTube Shorts videosu için 5 alternatif başlık (en fazla 60 "
            "karakter, 1 emoji) ve 3 alternatif ekran kancası (en fazla 4 kelime, BÜYÜK "
            "harf) öner. Kısa madde listesi olarak yaz.\n\n"
            f"Başlık: {ornek['baslik']}\nMetin: {ornek['script']}", max_tokens=2048)
        _o(f"[4] SEO OK ({sure}s):")
        for satir in cevap.splitlines()[:12]:
            if satir.strip():
                _o(f"    {satir.strip()}")
    except Exception as e:
        _o(f"[4] SEO HATA: {_hata(e)}")

    # 5) Görsel anlama: kanal banner'ını değerlendir (kapak denetimi provası)
    try:
        cevap, sure, _ = _sohbet(model, [
            {"type": "image_url", "image_url": {"url": _png_data_url("assets/marka/banner.png")}},
            {"type": "text", "text": "Bu bir YouTube kanal görseli. Üzerindeki yazıyı oku, "
             "okunabilirliğini ve dikkat çekiciliğini 10 üzerinden puanla, 2 kısa "
             "iyileştirme önerisi ver. En fazla 5 satır."}], max_tokens=2048)
        _o(f"[5] GÖRSEL OK ({sure}s):")
        for satir in cevap.splitlines()[:6]:
            if satir.strip():
                _o(f"    {satir.strip()}")
    except Exception as e:
        _o(f"[5] GÖRSEL HATA: {_hata(e)}")

    # 6) Video anlama: siyah kare içeren test klibi (yükleme öncesi kalite kontrol provası)
    klip = _test_klibi()
    if not klip:
        _o("[6] VİDEO atlandı: ffmpeg yok ya da klip üretilemedi.")
    else:
        url = "data:video/mp4;base64," + base64.b64encode(open(klip, "rb").read()).decode()
        soru = {"type": "text", "text": "Bu kısa videoyu izle. Siyah/boş ekran, donma ya da "
                "bozuk görüntü var mı? Varsa yaklaşık hangi saniyede? En fazla 3 satır."}
        # OpenAI-uyumlu tek standart yok; iki yaygın biçimi sırayla dene.
        for ad, parca in (("video_url", {"type": "video_url", "video_url": {"url": url}}),
                          ("input_video", {"type": "input_video", "video_url": url})):
            try:
                cevap, sure, _ = _sohbet(model, [parca, soru], max_tokens=2048)
                _o(f"[6] VİDEO OK ({ad}, {sure}s): {' '.join(cevap.split())[:300]}")
                break
            except Exception as e:
                _o(f"[6] VİDEO HATA ({ad}): {_hata(e)}")

    _yaz()


def _yaz():
    try:
        os.makedirs("output", exist_ok=True)
        with open("output/mimo_rapor.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(OZET))
    except Exception:
        pass
    print("\n===== MIMO DENEME OZETI =====")
    for s in OZET:
        print("  " + s)
    print("=============================")


if __name__ == "__main__":
    main()
