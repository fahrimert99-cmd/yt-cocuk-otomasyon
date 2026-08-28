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
import os, json, re, glob, datetime as dt
import smtplib, ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.header import Header
from googleapiclient.discovery import build
from youtube_yukle import _kimlik


def _ttf_bul(isim):
    """Sistemde bir TTF fontu adına göre arar (ubuntu runner'da DejaVu hazır gelir)."""
    for taban in ("/usr/share/fonts", "/usr/local/share/fonts",
                  os.path.expanduser("~/.fonts")):
        vur = glob.glob(f"{taban}/**/{isim}", recursive=True)
        if vur:
            return vur[0]
    return None


# emoji / dekoratif semboller (DejaVu bunları içermez → temizlenir)
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2190-\u21FF\u2B00-\u2BFF\uFE0F]"
)


def _pdf_uret(md_metin, cikti="analiz_rapor.pdf"):
    """Rapor markdown'ını Türkçe destekli, tabloları hizalı bir PDF'e döker.
    fpdf2 veya uygun font yoksa None döner (mail düz metne düşer)."""
    try:
        from fpdf import FPDF
        from fpdf.enums import WrapMode
    except Exception:
        print("  [pdf atlandı: fpdf2 kurulu değil]")
        return None
    reg = _ttf_bul("DejaVuSans.ttf")
    bold = _ttf_bul("DejaVuSans-Bold.ttf")
    mono = _ttf_bul("DejaVuSansMono.ttf")
    if not (reg and mono):
        print("  [pdf atlandı: DejaVu fontları bulunamadı]")
        return None

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.set_margins(12, 12, 12)
    pdf.add_page()
    pdf.add_font("dj", "", reg)
    pdf.add_font("dj", "B", bold or reg)
    pdf.add_font("mono", "", mono)

    def yaz(font, stil, boy, metin):
        pdf.set_font(font, stil, boy)
        pdf.multi_cell(0, boy * 0.55, _EMOJI.sub("", metin).rstrip() or " ")

    satirlar = md_metin.split("\n")
    i = 0
    while i < len(satirlar):
        s = satirlar[i].rstrip()
        # --- tablo bloğu: fpdf2 tablo API'siyle otomatik hizalı render ---
        if s.startswith("|"):
            blok = []
            while i < len(satirlar) and satirlar[i].lstrip().startswith("|"):
                blok.append(satirlar[i].strip())
                i += 1
            # ayraç satırlarını (|---|---|) at, hücreleri ayrıştır + emoji temizle
            rows = []
            for r in blok:
                if re.fullmatch(r"\|[\s:\-|]+\|", r):
                    continue
                rows.append([_EMOJI.sub("", c.strip()) for c in r.strip("|").split("|")])
            if rows:
                sut = max(len(r) for r in rows)
                rows = [r + [""] * (sut - len(r)) for r in rows]
                pdf.set_font("dj", "", 8)
                with pdf.table(first_row_as_headings=True, line_height=5,
                               width=pdf.epw, wrapmode=WrapMode.CHAR) as tablo:
                    for r in rows:
                        satir = tablo.row()
                        for c in r:
                            satir.cell(c)
                pdf.ln(2)
            continue
        # --- başlıklar ---
        if s.startswith("# "):
            yaz("dj", "B", 15, s[2:]); pdf.ln(1)
        elif s.startswith("## "):
            pdf.ln(1); yaz("dj", "B", 12, s[3:])
        elif s.startswith("### "):
            yaz("dj", "B", 10, s[4:])
        elif s.startswith("> "):
            yaz("dj", "", 8, s[2:])
        elif s:
            yaz("dj", "", 9, s.replace("**", ""))
        else:
            pdf.ln(2)
        i += 1

    pdf.output(cikti)
    return cikti


def _mail_gonder(konu, govde, ek=None):
    """Raporu Gmail SMTP ile e-postayla gönderir (MAIL_USER/MAIL_PASS ayarlıysa).
    MAIL_PASS = Gmail 'uygulama şifresi' (normal şifre değil). MAIL_TO boşsa
    gönderene atılır."""
    user = os.environ.get("MAIL_USER", "").strip().strip("'\"")
    # app password: tüm boşlukları (nbsp dahil) ve yanlışlıkla kopyalanan
    # tırnak işaretlerini temizle. Gmail app password 16 harf, boşluksuz olmalı.
    pw = re.sub(r"\s+", "", os.environ.get("MAIL_PASS", "")).strip("'\"")
    to = os.environ.get("MAIL_TO", "").strip() or user
    if not (user and pw and to):
        print("  [mail atlandı: MAIL_USER/MAIL_PASS secret'ları ayarlı değil]")
        return
    if ek and os.path.exists(ek):
        msg = MIMEMultipart()
        msg.attach(MIMEText(govde, "plain", "utf-8"))
        with open(ek, "rb") as f:
            parca = MIMEApplication(f.read(), _subtype="pdf")
        parca.add_header("Content-Disposition", "attachment",
                         filename=os.path.basename(ek))
        msg.attach(parca)
    else:
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
    except smtplib.SMTPAuthenticationError as e:
        print(f"  ! mail gönderilemedi (kimlik reddedildi): {str(e)[:160]}")
        print("    → MAIL_PASS bir Gmail 'uygulama şifresi' olmalı (normal şifre DEĞİL);")
        print("      hesapta 2 Adımlı Doğrulama açık olmalı ve MAIL_USER app password'ün")
        print("      ait olduğu Gmail adresiyle aynı olmalı. Secret'ları güncelleyin.")
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

def _degerlendirme(videolar, format_ozet, tema_ozet, top, yeni):
    """Ham verilerden yorum + SOMUT AKSİYON önerileri üretir (API'siz, deterministik).
    Döndürür: (markdown_satirlari, json_dict). Rapora 'ne yapmalısın' bölümü ekler."""
    bulgular = []   # markdown madde satırları
    aksiyonlar = [] # numaralı somut adımlar

    genel_ort = _ort(videolar, "izlenme")

    # 1) TEMA: en güçlü / en zayıf (ort. izlenmeye göre)
    temalar = sorted(tema_ozet.items(), key=lambda x: -x[1]["ort_izlenme"])
    if temalar:
        en_iyi_t, ei = temalar[0]
        bulgular.append(f"- 🎯 **En çok tutan tema: {en_iyi_t}** — ort. {ei['ort_izlenme']} izlenme "
                        f"({ei['video']} video). Bu damardan daha çok konu üret.")
        aksiyonlar.append(f"`senaryolar.json`'a **{en_iyi_t}** temasında yeni konular ekle "
                          f"(en çok izlenen damar).")
        if len(temalar) >= 2:
            en_kotu_t, ek = temalar[-1]
            # anlamlı olması için en az 2 video olsun ve en iyiden belirgin düşük olsun
            if ek["video"] >= 2 and ei["ort_izlenme"] >= max(1, ek["ort_izlenme"]) * 1.5:
                bulgular.append(f"- ⚠️ **En zayıf tema: {en_kotu_t}** — ort. {ek['ort_izlenme']} izlenme "
                                f"({ek['video']} video). Bu temada üretimi azalt ya da başlık/kancayı güçlendir.")
                aksiyonlar.append(f"**{en_kotu_t}** temasında yeni üretimi azalt; mevcutların başlık/kapağını gözden geçir.")

    # 2) FORMAT: short vs uzun hangisi daha çok izleniyor
    if len(format_ozet) >= 2:
        fmt = sorted(format_ozet.items(), key=lambda x: -x[1]["ort_izlenme"])
        (f1, d1), (f2, d2) = fmt[0], fmt[-1]
        bulgular.append(f"- 📐 **{f1}** formatı daha çok izleniyor: ort. {d1['ort_izlenme']} vs "
                        f"{f2} {d2['ort_izlenme']}. Ağırlığı **{f1}**'e kaydırmayı düşün.")

    # 3) ETKİLEŞİM: en yüksek etkileşim oranı hangi temada
    etk = [(t, d) for t, d in tema_ozet.items() if d["toplam_izlenme"] > 0]
    if etk:
        et, ed = max(etk, key=lambda x: x[1]["etkilesim_orani"])
        bulgular.append(f"- 💬 **En yüksek etkileşim: {et}** (%{ed['etkilesim_orani']}). "
                        f"İzleyici en çok burada yorum/beğeni bırakıyor — CTA'yı bu içerikte koru.")

    # 4) TOP10: en çok izlenen 10 videoda baskın tema
    if top:
        say = {}
        for v in top:
            say[v["tema"]] = say.get(v["tema"], 0) + 1
        baskin, n = max(say.items(), key=lambda x: x[1])
        if n >= 3:
            bulgular.append(f"- 🏆 En çok izlenen 10 videonun **{n}'i {baskin}** teması — "
                            f"kanıtlanmış damar, önceliklendir.")

    # 5) TREND: son 7 gün ortalaması genel ortalamaya göre
    if yeni:
        s7 = _ort(yeni, "izlenme")
        if s7 >= genel_ort:
            bulgular.append(f"- 📈 **Trend iyi:** son 7 gün ort. {s7} ≥ genel ort. {genel_ort}. "
                            f"Mevcut yönü sürdür.")
        else:
            bulgular.append(f"- 📉 **Dikkat:** son 7 gün ort. {s7} < genel ort. {genel_ort}. "
                            f"Son üretimleri gözden geçir (başlık/kapak/tema seçimi).")
            aksiyonlar.append("Son 7 günün düşük performansını incele: başlık kancası ve kapak yeterince çarpıcı mı?")

    if not bulgular:
        bulgular.append("- Henüz güçlü bir sinyal yok (az veri). Birkaç video daha biriktikçe öneriler netleşir.")
    if not aksiyonlar:
        aksiyonlar.append("Mevcut yönü koru; bir sonraki denetimde tema/format sinyallerine göre ayar yap.")

    return bulgular, aksiyonlar


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

    # verilerden yorum + somut aksiyon önerileri (API'siz)
    bulgular, aksiyonlar = _degerlendirme(videolar, format_ozet, tema_ozet, top, yeni)

    rapor = {
        "tarih": bugun,
        "kanal": {"abone": kanal_ist.get("subscriberCount"),
                  "toplam_izlenme": kanal_ist.get("viewCount"),
                  "video_sayisi": kanal_ist.get("videoCount")},
        "degerlendirme": {"bulgular": bulgular, "aksiyonlar": aksiyonlar},
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
    # --- ÖNCE 'ne yapmalısın': değerlendirme + aksiyonlar en üstte ---
    L.append("## 🧭 Değerlendirme & Öneriler")
    L.extend(bulgular)
    L.append("\n### ✅ Sıradaki aksiyonlar")
    for i, a in enumerate(aksiyonlar, 1):
        L.append(f"{i}. {a}")
    L.append("")
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
    # Günlük raporu e-postayla gönder (kurulmuşsa) — rapor PDF ek olarak gider,
    # PDF üretilemezse mail gövdesinde düz metin olarak.
    pdf_yol = _pdf_uret(md)
    if pdf_yol:
        print(f"  ✓ PDF üretildi: {pdf_yol}")
    govde = ("Merhaba,\n\nGünlük kanal denetim raporu ekte PDF olarak yer alıyor.\n"
             if pdf_yol else md)
    _mail_gonder(f"📊 Kanal Denetim Raporu — {bugun}", govde, ek=pdf_yol)

if __name__ == "__main__":
    main()
