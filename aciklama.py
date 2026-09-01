#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Video açıklaması (description) OLUŞTURUCU — SEO + marka footer.
Her videonun konu kancasını korur, üstüne TUTARLI marka footer'ı ekler:
güçlü CTA + yayın saatleri + handle + kanal linki + zengin hashtag.
senaryolar.json'daki açıklamaları elle değiştirmeden çalışır.
"""
import re

SABIT_ETIKET = ["tüketicituzağı", "tasarruf", "paranıkoru", "farkındalık", "tuzak"]


def _hashtagle(kelime):
    h = re.sub(r"[^0-9a-zçğıiöşü]", "", (kelime or "").lower().replace(" ", ""))
    return ("#" + h) if len(h) >= 2 else ""


def olustur(veri, cfg=None):
    cfg = cfg or {}
    ham = (veri.get("aciklama") or "").strip()
    # ilk paragraf = konu kancası; mevcut footer/hashtag'i ATıp yeniden kurarız
    kanca = ham.split("\n\n")[0].strip() if ham else (veri.get("kanca") or "").strip()
    kanca = re.sub(r"\n?#\S+.*$", "", kanca).strip()  # satır sonundaki eski hashtag'i temizle

    ad = str(cfg.get("marka_ad", "TUZAK AVCISI") or "TUZAK AVCISI").strip()
    handle = str(cfg.get("marka_handle", "") or "").strip()

    # hashtag: videonun kendi etiketleri + sabit marka etiketleri (tekrarsız, ilk 12)
    etik = veri.get("etiketler") or []
    if isinstance(etik, str):
        etik = [e.strip() for e in etik.split(",") if e.strip()]
    hashtags = []
    for t in list(etik) + SABIT_ETIKET:
        h = _hashtagle(t)
        if h and h not in hashtags:
            hashtags.append(h)
    hashtags = hashtags[:12]

    satir = []
    if kanca:
        satir += [kanca, ""]
    satir.append(f"🎯 {ad} — seni kandıran oyunları çözüyoruz.")
    satir.append("🔔 Her gün yeni bir tüketici tuzağı — 12:00 & 20:00. Abone ol, bir daha kanma!")
    if handle:
        h2 = handle if handle.startswith("@") else "@" + handle
        satir.append(f"👉 {h2}  |  youtube.com/{h2}")
    if hashtags:
        satir += ["", " ".join(hashtags)]
    return "\n".join(satir)


if __name__ == "__main__":
    import json
    sen = json.load(open("senaryolar.json", encoding="utf-8-sig"))
    cfg = json.load(open("config.json", encoding="utf-8-sig"))
    print(olustur(sen[0], cfg))
    print("\n" + "=" * 60 + "\n")
    print(olustur(sen[100], cfg))
