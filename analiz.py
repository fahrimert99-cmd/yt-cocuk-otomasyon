#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DENETİM / ANALİZ — YouTube istatistiklerini otomatik çeker, tema/format bazında
özetler ve repoya rapor yazar (analiz_rapor.md + analiz_rapor.json).
Böylece performans verisi elle gönderilmeden kendiliğinden birikir; haftalık
iyileştirme kararları bu rapora dayanır.

Kullanır: youtube_yukle._kimlik() (mevcut OAuth refresh token, youtube.force-ssl).
Temel metrikler (izlenme/beğeni/yorum) bu izinle çekilir. Retention/CTR gibi
DERİN metrikler YouTube Analytics API + yt-analytics.readonly izni ister; yoksa
o bölüm atlanır (rapor yine üretilir).
"""
import os, json, re, datetime as dt
import smtplib, ssl
from email.mime.text import MIMEText
from email.header import Header
from googleapiclient.discovery import build
from youtube_yukle import _kimlik


def _mail_gonder(konu, govde):
    """Raporu Gmail SMTP ile e-postayla gönderir (MAIL_USER/MAIL_PASS ayarlıysa).
    MAIL_PASS = Gmail 'uygulama şifresi' (normal şifre değil). MAIL_TO boşsa
    gönderene atılır."""
    user = os.environ.get("MAIL_USER", "").strip()
    pw = os.environ.get("MAIL_PASS", "").strip()
    to = os.environ.get("MAIL_TO", "").strip() or user
    if not (user and pw and to):
        print("  [mail atlandı: MAIL_USER/MAIL_PASS secret'ları ayarlı değil]")
        return
    msg = MIMEText(govde, "plain", "utf-8")
    msg["Subject"] = Header(konu, "utf-8")
    msg["From"] = user
    msg["To"] = to
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=60) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(user, pw)
            s.sendmail(user, [to], msg.as_string())
        print(f"  ✓ rapor e-postayla gönderildi: {to}")
    except Exception as e:
        print(f"  ! mail gönderilemedi: {str(e)[:160]}")

# --- tema tespiti (baslik anahtar kelimeleriyle) ---
GIZEM_KW = ["BERMUDA", "OKYANUS", "PİRAMİT", "ATLANTİS", "GİZEM", "SIR", "KAYIP", "UZAY",
            "ANTİK", "MUMYA", "LANET", "NAZCA", "GÖBEKLİTEPE", "MAYA", "POMPEİ",
            "ANTARKTİKA", "SİNYAL", "EVREN", "STONEHENGE", "PASKALYA", "KARA DELİK",
            "VOYNICH", "TUNGUSKA", "DYATLOV", "ROANOKE", "ANTİKYTHERA", "TERRAKOTA",
            "MACHU", "SAHRA", "LOCH NESS", "DİNOZOR", "AMELIA", "İSKENDERİYE", "PETRA",
            "RÜYA", "MU", "KANYON", "ZAMAN", "UFO", "SFENKS", "YANILDI", "GÖNDERDİ",
            "KAYBOL", "DERİNLİK", "ESRAR", "FİLO"]
TUZAK_KW = ["TUZAK", "FİYAT", "MARKET", "İNDİRİM", "KART", "KREDİ", "KASA", "PAKET",
            "REKLAM", "MENÜ", "ABONELİK", "BEDAVA", "ÜCRETSİZ", "KAMPANYA", "SEPET",
            "OYUNCAK", "KARGO", "TAKSİT", "SADAKAT", "KUAFÖR", "OTOPARK", "ÇİZİLİ",
            "SİNEMA", "MISIR", "SÜT", "RAF", "VİTRİN", "KUPON", "HEDİYE"]

def _tema(baslik):
    b = (baslik or "").upper()
    g = sum(1 for k in GIZEM_KW if k in b)
    t = sum(1 for k in TUZAK_KW if k in b)
    if g > t: return "gizem"
    if t > g: return "tuzak"
    return "diger"

def _sure_sn(iso):
    """ISO8601 süre (PT#M#S) -> saniye."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m: return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s

def _format(sn):
    return "short" if sn and sn < 100 else "uzun"

def _videolar(yt):
    """Kanalın son ~50 videosunu (istatistikleriyle) getir."""
    ch = yt.channels().list(part="contentDetails,statistics", mine=True).execute()
    it = ch.get("items", [])
    if not it: return [], {}
    kanal_ist = it[0].get("statistics", {})
    uploads = it[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    vid_ids = []
    tok = None
    while len(vid_ids) < 60:
        pl = yt.playlistItems().list(part="contentDetails", playlistId=uploads,
                                     maxResults=50, pageToken=tok).execute()
        vid_ids += [i["contentDetails"]["videoId"] for i in pl.get("items", [])]
        tok = pl.get("nextPageToken")
        if not tok: break
    videolar = []
    for i in range(0, len(vid_ids), 50):
        grup = vid_ids[i:i + 50]
        r = yt.videos().list(part="snippet,statistics,contentDetails", id=",".join(grup)).execute()
        for v in r.get("items", []):
            st = v.get("statistics", {}); sn = _sure_sn(v["contentDetails"].get("duration"))
            videolar.append({
                "id": v["id"], "baslik": v["snippet"]["title"],
                "yayin": v["snippet"]["publishedAt"][:10],
                "izlenme": int(st.get("viewCount", 0)),
                "begeni": int(st.get("likeCount", 0)),
                "yorum": int(st.get("commentCount", 0)),
                "sure_sn": sn, "format": _format(sn), "tema": _tema(v["snippet"]["title"]),
            })
    return videolar, kanal_ist

def _ort(lst, alan):
    v = [x[alan] for x in lst]
    return round(sum(v) / len(v)) if v else 0

def _grup_ozet(videolar, anahtar):
    gruplar = {}
    for v in videolar:
        gruplar.setdefault(v[anahtar], []).append(v)
    out = {}
    for k, g in gruplar.items():
        toplam_izlenme = sum(x["izlenme"] for x in g)
        etk = sum(x["begeni"] + x["yorum"] for x in g)
        out[k] = {
            "video": len(g),
            "ort_izlenme": _ort(g, "izlenme"),
            "toplam_izlenme": toplam_izlenme,
            "etkilesim_orani": round(etk / toplam_izlenme * 100, 2) if toplam_izlenme else 0.0,
        }
    return out

def main():
    yt = build("youtube", "v3", credentials=_kimlik())
    videolar, kanal_ist = _videolar(yt)
    if not videolar:
        print("Video bulunamadı."); return
    bugun = dt.date.today().isoformat()
    format_ozet = _grup_ozet(videolar, "format")
    tema_ozet = _grup_ozet(videolar, "tema")
    top = sorted(videolar, key=lambda x: -x["izlenme"])[:10]
    # son 7 gün yayınlananlar
    esik = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    yeni = [v for v in videolar if v["yayin"] >= esik]

    rapor = {
        "tarih": bugun,
        "kanal": {"abone": kanal_ist.get("subscriberCount"),
                  "toplam_izlenme": kanal_ist.get("viewCount"),
                  "video_sayisi": kanal_ist.get("videoCount")},
        "format_ozet": format_ozet,
        "tema_ozet": tema_ozet,
        "top10": [{"baslik": v["baslik"], "izlenme": v["izlenme"], "tema": v["tema"],
                   "format": v["format"]} for v in top],
        "son7gun": [{"baslik": v["baslik"], "izlenme": v["izlenme"], "tema": v["tema"],
                     "format": v["format"], "yayin": v["yayin"]} for v in yeni],
    }
    with open("analiz_rapor.json", "w", encoding="utf-8") as f:
        json.dump(rapor, f, ensure_ascii=False, indent=2)

    # --- insan-okunur markdown ---
    L = []
    L.append(f"# 📊 Kanal Denetim Raporu — {bugun}\n")
    k = rapor["kanal"]
    L.append(f"**Abone:** {k['abone']}  |  **Toplam izlenme:** {k['toplam_izlenme']}  |  **Video:** {k['video_sayisi']}\n")
    L.append("## Format performansı (son ~50 video)")
    L.append("| Format | Video | Ort. izlenme | Toplam izlenme | Etkileşim % |")
    L.append("|--------|-------|--------------|----------------|-------------|")
    for f, d in sorted(format_ozet.items()):
        L.append(f"| {f} | {d['video']} | {d['ort_izlenme']} | {d['toplam_izlenme']} | {d['etkilesim_orani']} |")
    L.append("\n## Tema performansı")
    L.append("| Tema | Video | Ort. izlenme | Toplam izlenme | Etkileşim % |")
    L.append("|------|-------|--------------|----------------|-------------|")
    for t, d in sorted(tema_ozet.items(), key=lambda x: -x[1]["ort_izlenme"]):
        L.append(f"| {t} | {d['video']} | {d['ort_izlenme']} | {d['toplam_izlenme']} | {d['etkilesim_orani']} |")
    L.append("\n## En çok izlenen 10 video")
    L.append("| # | Başlık | İzlenme | Tema | Format |")
    L.append("|---|--------|---------|------|--------|")
    for i, v in enumerate(top, 1):
        L.append(f"| {i} | {v['baslik'][:45]} | {v['izlenme']} | {v['tema']} | {v['format']} |")
    L.append(f"\n## Son 7 günde yayınlananlar ({len(yeni)})")
    if yeni:
        L.append("| Başlık | İzlenme | Tema | Format | Yayın |")
        L.append("|--------|---------|------|--------|-------|")
        for v in sorted(yeni, key=lambda x: -x["izlenme"]):
            L.append(f"| {v['baslik'][:40]} | {v['izlenme']} | {v['tema']} | {v['format']} | {v['yayin']} |")
    L.append("\n> Not: Retention (izlenme %) ve CTR gibi derin metrikler için "
             "YouTube Analytics izni (yt-analytics.readonly) gerekir; şu an temel "
             "metrikler (izlenme/beğeni/yorum) raporlanıyor.")
    md = "\n".join(L) + "\n"
    with open("analiz_rapor.md", "w", encoding="utf-8") as f:
        f.write(md)
    print(f"✓ Rapor yazıldı: analiz_rapor.md + analiz_rapor.json ({len(videolar)} video)")
    print(f"  Format: {format_ozet}")
    print(f"  Tema:   {tema_ozet}")
    # Günlük raporu e-postayla gönder (kurulmuşsa)
    _mail_gonder(f"📊 Kanal Denetim Raporu — {bugun}", md)

if __name__ == "__main__":
    main()
