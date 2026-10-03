#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bir rakip kanalı YouTube Data API ile SALT OKUNUR inceler.

Kullanım: RAKIP="@benonurulger,@benonurülger" python3 rakip_kanal.py
Kanal bulunamazsa ada göre kanal araması yapar (100 kota birimi).
Çıktı: log + rakip_kanal.json. Kendi kanalımıza hiçbir şey yazmaz.
"""
from __future__ import annotations

import json
import os
import re
import statistics
from collections import Counter
from datetime import datetime, timezone

from googleapiclient.discovery import build

from analytics_rapor import _creds


def _sure_sn(iso):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def kanal_bul(yt, adaylar):
    for a in adaylar:
        h = a.strip().lstrip("@")
        if not h:
            continue
        r = yt.channels().list(part="id", forHandle=h).execute()
        if r.get("items"):
            print(f"[rakip] handle bulundu: @{h}")
            return r["items"][0]["id"]
    q = adaylar[0].strip().lstrip("@")
    r = yt.search().list(part="snippet", q=q, type="channel", maxResults=5).execute()
    print("[rakip] handle bulunamadı; arama sonuçları:")
    for it in r.get("items", []):
        print(f"   - {it['snippet']['channelTitle']} ({it['id']['channelId']})")
    return r["items"][0]["id"]["channelId"] if r.get("items") else None


def main():
    adaylar = [x for x in os.environ.get("RAKIP", "@benonurulger").split(",") if x.strip()]
    yt = build("youtube", "v3", credentials=_creds())
    kid = kanal_bul(yt, adaylar)
    if not kid:
        print("[rakip] kanal bulunamadı"); return
    ch = yt.channels().list(part="snippet,statistics,contentDetails,brandingSettings",
                            id=kid).execute()["items"][0]
    sn, st = ch["snippet"], ch["statistics"]
    yukleme = ch["contentDetails"]["relatedPlaylists"]["uploads"]

    ids, tok = [], None
    while len(ids) < 200:
        r = yt.playlistItems().list(part="contentDetails", playlistId=yukleme,
                                    maxResults=50, pageToken=tok).execute()
        ids += [i["contentDetails"]["videoId"] for i in r.get("items", [])]
        tok = r.get("nextPageToken")
        if not tok:
            break

    videolar = []
    simdi = datetime.now(timezone.utc)
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part="snippet,statistics,contentDetails",
                             id=",".join(ids[i:i + 50])).execute()
        for v in r.get("items", []):
            vs, vst = v["snippet"], v.get("statistics", {})
            yay = datetime.fromisoformat(vs["publishedAt"].replace("Z", "+00:00"))
            gun = max(1, (simdi - yay).days)
            iz = int(vst.get("viewCount", 0))
            videolar.append({
                "id": v["id"], "baslik": vs["title"], "yayin": vs["publishedAt"],
                "sure_sn": _sure_sn(v["contentDetails"].get("duration")),
                "izlenme": iz, "begeni": int(vst.get("likeCount", 0)),
                "yorum": int(vst.get("commentCount", 0)), "gunluk": round(iz / gun, 1),
                "etiket": vs.get("tags", [])[:15],
                "aciklama": (vs.get("description") or "")[:300],
            })

    shorts = [v for v in videolar if v["sure_sn"] <= 180]
    uzun = [v for v in videolar if v["sure_sn"] > 180]
    saat = Counter(datetime.fromisoformat(v["yayin"].replace("Z", "+00:00")).hour
                   for v in videolar)
    tarihler = sorted(v["yayin"] for v in videolar)

    def ozet(lst):
        if not lst:
            return {}
        iz = [v["izlenme"] for v in lst]
        et = [(v["begeni"] + v["yorum"]) / v["izlenme"] * 100 for v in lst if v["izlenme"]]
        return {"adet": len(lst), "ort_izlenme": round(statistics.mean(iz)),
                "medyan_izlenme": round(statistics.median(iz)),
                "ort_sure_sn": round(statistics.mean(v["sure_sn"] for v in lst)),
                "etkilesim_orani_%": round(statistics.mean(et), 2) if et else 0}

    rapor = {
        "kanal": {"id": kid, "baslik": sn["title"], "handle": sn.get("customUrl"),
                  "acilis": sn["publishedAt"], "ulke": sn.get("country"),
                  "aciklama": sn.get("description", "")[:800],
                  "abone": st.get("subscriberCount"), "toplam_izlenme": st.get("viewCount"),
                  "video_sayisi": st.get("videoCount"),
                  "anahtar_kelimeler": ch.get("brandingSettings", {}).get("channel", {}).get("keywords")},
        "incelenen_video": len(videolar),
        "ilk_son_yayin": [tarihler[0], tarihler[-1]] if tarihler else None,
        "shorts": ozet(shorts), "uzun": ozet(uzun),
        "yayin_saati_utc": dict(saat.most_common(6)),
        "en_iyi_20": sorted(videolar, key=lambda v: -v["izlenme"])[:20],
        "son_20": sorted(videolar, key=lambda v: v["yayin"], reverse=True)[:20],
        "etiket_frekans": Counter(t.lower() for v in videolar for t in v["etiket"]).most_common(30),
    }
    with open("rakip_kanal.json", "w", encoding="utf-8") as f:
        json.dump(rapor, f, ensure_ascii=False, indent=1)
    print("RAKIP_RAPOR_BASLA")
    print(json.dumps(rapor, ensure_ascii=False, indent=1))
    print("RAKIP_RAPOR_BITTI")


if __name__ == "__main__":
    main()
