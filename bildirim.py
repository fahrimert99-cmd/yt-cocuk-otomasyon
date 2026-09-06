#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TELEGRAM BİLDİRİM — hepsi NON-FATAL, ek bağımlılık YOK (saf urllib).

Anahtar yoksa (TELEGRAM_TOKEN / TELEGRAM_CHAT_ID) sessizce atlar; hiçbir
koşulda çağıran akışı kırmaz. Böylece üretim/yükleme yoluna güvenle eklenir.

Env:
  TELEGRAM_TOKEN    BotFather'dan alınan bot token'ı
  TELEGRAM_CHAT_ID  Bildirimin gideceği sohbet id'si

Kullanım (kod içinden):
  import bildirim as B
  B.mesaj("Video yayınlandı: ...")
  B.foto("output/son_kapak.jpg", "Bugünün kapağı")
  B.video("output/son_video.mp4", "Önizleme")

Kullanım (workflow'dan hata bildirimi):
  python3 bildirim.py "🚨 Otomasyon başarısız — <run linki>"
"""
import os, json, mimetypes, urllib.request, urllib.error

API = "https://api.telegram.org/bot{token}/{metod}"
MAX_METIN = 4000          # Telegram sınırı 4096; pay bırakıyoruz
MAX_DOSYA = 50 * 1024 * 1024   # bot API dosya sınırı ~50MB


def _ayar():
    """(token, chat_id) döner; biri bile yoksa (None, None)."""
    t = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
    c = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    return (t, c) if (t and c) else (None, None)


def acik():
    """Bildirim yapılandırılmış mı (log/teşhis için)."""
    return _ayar()[0] is not None


def _multipart(alanlar, dosya_alan=None, dosya_yol=None):
    """multipart/form-data gövdesi kurar -> (content_type, bayt)."""
    sinir = "----tuzakavcisi7f3b2a1c"
    parca = []
    for ad, deger in alanlar.items():
        parca.append(f"--{sinir}\r\n".encode())
        parca.append(f'Content-Disposition: form-data; name="{ad}"\r\n\r\n'.encode())
        parca.append(f"{deger}\r\n".encode())
    if dosya_alan and dosya_yol:
        ad_dosya = os.path.basename(dosya_yol)
        tur = mimetypes.guess_type(ad_dosya)[0] or "application/octet-stream"
        with open(dosya_yol, "rb") as f:
            icerik = f.read()
        parca.append(f"--{sinir}\r\n".encode())
        parca.append(
            f'Content-Disposition: form-data; name="{dosya_alan}"; '
            f'filename="{ad_dosya}"\r\n'.encode())
        parca.append(f"Content-Type: {tur}\r\n\r\n".encode())
        parca.append(icerik)
        parca.append(b"\r\n")
    parca.append(f"--{sinir}--\r\n".encode())
    return f"multipart/form-data; boundary={sinir}", b"".join(parca)


def _cagir(metod, alanlar, dosya_alan=None, dosya_yol=None, timeout=120):
    """Telegram API çağrısı. True/False döner; ASLA fırlatmaz."""
    token, chat = _ayar()
    if not token:
        return False
    alanlar = dict(alanlar)
    alanlar["chat_id"] = chat
    url = API.format(token=token, metod=metod)
    try:
        if dosya_yol:
            ctype, govde = _multipart(alanlar, dosya_alan, dosya_yol)
            req = urllib.request.Request(url, data=govde,
                                         headers={"Content-Type": ctype})
        else:
            govde = json.dumps(alanlar).encode()
            req = urllib.request.Request(
                url, data=govde, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        if not d.get("ok"):
            print(f"  [telegram: {metod} reddedildi: {str(d)[:120]}]")
            return False
        return True
    except urllib.error.HTTPError as he:
        try:
            det = he.read().decode()[:160]
        except Exception:
            det = ""
        print(f"  [telegram {metod} HTTP {he.code}: {det}]")
        return False
    except Exception as e:
        print(f"  [telegram {metod} hata: {type(e).__name__}: {str(e)[:100]}]")
        return False


def mesaj(metin):
    """Düz metin bildirim gönderir. True/False (non-fatal)."""
    if not (metin or "").strip():
        return False
    return _cagir("sendMessage", {"text": str(metin)[:MAX_METIN],
                                  "disable_web_page_preview": False})


def _dosya_gonder(metod, alan, yol, aciklama=""):
    if not yol or not os.path.exists(yol):
        return False
    if os.path.getsize(yol) > MAX_DOSYA:
        return mesaj(f"{aciklama} (dosya 50MB'ı aştığı için gönderilemedi: "
                     f"{os.path.basename(yol)})")
    return _cagir(metod, {"caption": str(aciklama)[:1000]}, alan, yol)


def foto(yol, aciklama=""):
    """Görsel gönderir (kapak vb.)."""
    return _dosya_gonder("sendPhoto", "photo", yol, aciklama)


def video(yol, aciklama=""):
    """Video gönderir (önizleme klibi vb.)."""
    return _dosya_gonder("sendVideo", "video", yol, aciklama)


def belge(yol, aciklama=""):
    """Dosya olarak gönderir (rapor PDF vb.)."""
    return _dosya_gonder("sendDocument", "document", yol, aciklama)


if __name__ == "__main__":
    import sys
    if not acik():
        print("Telegram yapılandırılmamış (TELEGRAM_TOKEN/TELEGRAM_CHAT_ID yok) — atlandı.")
        raise SystemExit(0)
    metin = " ".join(sys.argv[1:]) or "Test bildirimi"
    print("gönderildi ✓" if mesaj(metin) else "gönderilemedi")
