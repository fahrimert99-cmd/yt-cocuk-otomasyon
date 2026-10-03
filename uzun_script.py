# uzun_script.py — UZUN (yatay) video metni uretir.
# Varsayilan tema "tuketici_belgesel": 8-12 dk (~1300-1600 kelime) marka/sirket
# hikayesi + tuketiciye kurulan tuzak (Onur Ulger tarzi "X Neden Y?" belgeseli).
# Eski ~3 dk "gizem" temasi config.uzun_tema="gizem" ile hala secilebilir.
import os, re, json, time, urllib.request
from ai_script import _gemini, _poll_post, _poll_get, _temizle, _claude, _claude_key

# Guncel UCRETSIZ katman modelleri; anahtarin erisebildigi ilki secilir.
GEMINI_MODELS = ["gemini-3.5-flash-lite", "gemini-2.5-flash"]

# Model başına çıktı tavanı: gemini-2.5-flash düşünme tokenlarını da bu bütçeden
# harcıyor (16k'da uzun JSON yarıda kesiliyordu).
GEMINI_MAX_CIKTI = {"gemini-2.5-flash": 65536}

def _gemini_uzun(prompt, key, model):
    # ai_script._gemini ile ayni, ama maxOutputTokens buyuk (uzun JSON kesilmesin).
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.9, "maxOutputTokens": GEMINI_MAX_CIKTI.get(model, 16384),
                                 "responseMimeType": "application/json"}}
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    # 2.5-flash düşünürken 120 sn'yi aşabiliyordu (zaman aşımı) -> 300 sn.
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.loads(r.read().decode())
    return d["candidates"][0]["content"]["parts"][0]["text"]

UZUN_PROMPT = """BAŞLIK: {baslik}
Bu başlık için, YouTube'da YATAY bir "gizem / gerçek olay" belgesel-anlatım videosu için Türkçe seslendirme metni yaz.
Ton: merak uyandıran, hafif gerilimli ama güven veren bir anlatıcı; izleyiciyi bir gizemin/olayın peşine takan, sürükleyici belgesel dili.
Uzunluk: yaklaşık 400 kelime (~2,5-3 dakika seslendirme). Bilgiler DOĞRU olsun, uydurma istatistik/tarih verme; kesin bilinmeyen yerde "kesin olarak bilinmiyor" de ve teori olduğunu belirt.
Yapı — RETENTION için kritik: SOĞUK AÇILIŞ ile başla (ilk cümle çarpıcı bir soru ya da merak boşluğu; izleyici ilk 3 saniyede DURSUN). Sonra bölümler halinde derinleştir:
(1) gizemi/olayı sahnele: nerede, ne zaman, ne oldu, (2) bilinen gerçekler ve kanıtlar, (3) teoriler ve olasılıklar, (4) en çarpıcı detay / dönüm noktası ("ama sonra işler tuhaflaşıyor" gibi açık döngülerle merak taze tut), (5) düşündüren güçlü kapanış + "bir sonraki gizem için abone ol" tarzı kısa merak-odaklı abone çağrısı.
Her 60-90 saniyede yeni bir soru/merak aç ki izleyici sonuna kadar kalsın.
Emoji YOK, madde YOK, başlık satırı YOK; düz akıcı paragraflar (tek metin).
Anlatımı 10-13 sahneye böl. Sahne 'metin'leri script'in SIRAYLA parçaları olsun (o an anlatılan şey).
Her sahne için 'gorsel': o cümlede anlatılan şeyi gösteren 2-4 KELİMELİK, SOMUT, ARANABİLİR İngilizce stok video anahtar kelimesi.
Somut nesne/mekân/eylem kullan; örnek: "supermarket shopping cart", "credit card payment", "shrinking product package", "child playing phone game".
YASAK: soyut/kavramsal ifadeler ("conceptual", "abstract", "cinematic shot", "shadowy figure", "coins dissolving" gibi). Başa "a"/"the" KOYMA, somut ismi başa yaz.
ÇOK ÖNEMLİ — TÜRKÇE YAZIM: 'script', 'baslik', 'aciklama', 'kanca' ve sahne 'metin' alanlarını KUSURSUZ Türkçe imlâ ile yaz.
Türkçe'ye özgü harfleri (ç, ğ, ı, İ, ö, ş, ü ve büyükleri Ç, Ğ, İ, Ö, Ş, Ü) HER ZAMAN ve EKSİKSİZ kullan.
Bu harfleri ASLA ASCII karşılıklarına (c, g, i, o, s, u) sadeleştirme; aksan/diakritik atlama. Örnek: "guclu" DEĞİL "güçlü", "cocuk" DEĞİL "çocuk", "sirri" DEĞİL "sırrı", "yasiyor" DEĞİL "yaşıyor".
(NOT: yalnızca 'gorsel' alanı İngilizce olacak; onun dışındaki tüm metin doğru Türkçe karakterlerle yazılır.)
SADECE şu JSON'u döndür:
{{"baslik":"...","aciklama":"2-3 cümle","etiketler":["e1","e2","e3","e4","e5","e6","e7","e8"],"kanca":"EN FAZLA 3 kelimelik ŞOK EDİCİ, kaydırmayı durduran, merak uyandıran Türkçe açılış (kapakta da kullanılır) - izleyici ilk 2 saniyede DURSUN; ZORUNLU, asla boş bırakma; örnek: 'GEMİLER NEDEN KAYBOLUYOR', 'KİM GÖNDERDİ', 'HERKES YANILDI'","script":"...","sahneler":[{{"metin":"...","gorsel":"cinematic english"}}]}}"""


# --- TÜKETİCİ BELGESELİ: PARÇALI ÜRETİM ------------------------------------
# Tek istekte ~1500 kelime + 50 sahnelik JSON, Gemini'de kısa kalıyor, bozuk JSON
# dönüyor ya da zaman aşımına düşüyordu. Önce PLAN (başlık, 9 bölüm, kapak,
# açıklama), sonra her bölüm AYRI istekte yazılır: küçük, güvenilir, uzunluğu
# kontrollü. Bölüm sınırları sahne indekslerine birebir dönüşür (zaman damgası).
_ORTAK = """KANAL: TUZAK AVCISI — YATAY, 8-12 dakikalık "tüketici belgeseli" (Türkçe).
KONUMLANDIRMA: Herkesin bildiği bir markanın/sektörün iş modelini bir HİKÂYE olarak anlat, sonra bu modelin TÜKETİCİYE nasıl yansıdığını (fark etmeden ödenen bedel, kurulan tuzak) göster ve somut korunma yolları ver. Amaç: "bunu bilen tüketici bir daha kanmaz".
TON: Sakin, meraklı, güven veren belgesel anlatıcısı; birinci tekil şahıs ("bu videoda ... bakıyoruz"); izleyiciye "sen" diye hitap. Abartısız, sansasyonsuz.
DOĞRULUK VE HUKUK (ÇOK ÖNEMLİ): Uydurma istatistik, tarih, alıntı, dava YAZMA; emin olmadığın sayı yerine nitel ifade kullan ("milyonlarca", "yıllar içinde"). Bir şirketi suç işlemekle SUÇLAMA ("yasadışı", "dolandırıyor" gibi hüküm yok); taktikleri "iş modeli", "tasarım tercihi", "pazarlama stratejisi" olarak anlat; tartışmalı konularda "eleştirmenlere göre" de. Şirketin mantığını da tüketicinin bedelini de adil göster.
TÜRKÇE YAZIM: Türkçe alanları KUSURSUZ imlâyla yaz; ç, ğ, ı, İ, ö, ş, ü harflerini ASLA ASCII'ye sadeleştirme. Yalnızca 'gorsel_prompt', 'gorsel' ve 'kapak_gorsel' İngilizce."""

# 9 bölüm: Toyota/BİM videolarından çıkan iskelet (yaklaşık kelime hedefleriyle)
BELGESEL_YAPI = [
    ("ÇERÇEVE HİKÂYE AÇILIŞI", 170, "Somut, gerçekçi bir kişi/vaka/sahneyle başla (örn. kuyrukta bekleyen bir müşteri, şaşırtan bir fiş). Başlıktaki soruyu sor, cevabın beklenenden farklı olduğunu ima et."),
    ("BEKLENMEDİK BAŞLANGIÇ", 160, "Hikâyenin sanıldığı yerde başlamadığını göster; kurucular, yıl, ilk fikir (yalnızca kamuya açık bilgiler)."),
    ("KISIT / ZORUNLULUK", 140, "Şirketi bu modele iten kısıt neydi?"),
    ("MEKANİZMA", 190, "Sistem nasıl çalışıyor? 3-5 kavramı ADIYLA ver ve gündelik örnekle açıkla."),
    ("BÜYÜME", 140, "Model şirketi nasıl büyüttü?"),
    ("TÜKETİCİ TARAFI", 190, "Bu model izleyicinin cüzdanına, alışkanlığına, dikkatine nasıl yansıyor? Fark edilmeyen maliyetler, psikolojik taktikler."),
    ("KRİZ / ELEŞTİRİ", 150, "Modelin karanlık tarafı, bir kriz ya da eleştiri; adil anlat."),
    ("KORUNMA REHBERİ", 180, "3-5 somut, uygulanabilir adım."),
    ("ÇERÇEVEYE DÖNÜŞ VE KAPANIŞ", 130, "Açılıştaki kişiye/vakaya geri dön, ana fikri tek cümlede bağla."),
]

PLAN_PROMPT = """BAŞLIK: {baslik}
{not_satiri}{ortak}

GÖREV: Bu videonun PLANINI çıkar (anlatım metnini değil). Bölüm sırası sabit:
{yapi}

Her bölüm için: 'baslik' = zaman damgasında görünecek merak uyandıran kısa cümle (örn. "Toyota'nın hata yapacak parası yoktu"); 'ozet' = o bölümde anlatılacak SOMUT bilgiler (2-4 cümle; isimler, yıllar, kavramlar — yalnızca kamuya açık bilgiler).
BAŞLIK KURALI: "<Marka/Konu> Neden ...?" ya da "<Marka> Nasıl ...?" kalıbında, en fazla 60 karakter, cümle düzeninde, emoji YOK. Verilen başlığı koru; yalnızca yazım hatası varsa düzelt.
AÇIKLAMA (zaman damgası YAZMA; emoji YOK; paragraflar arasında boş satır): (1) başlıktaki soru tek satır; (2) cevabın beklenen yerde olmadığını söyleyen 1-2 cümle; (3) "Bu videoda ..." diye başlayıp tarihçeyi, kavramları ve konuları sayan, "... inceliyorum." diye biten paragraf; (4) videonun cevapladığı 3-4 merak sorusu, her biri ayrı satırda; (5) tek cümlelik vurucu sonuç ("Belki de asıl ürün ... değil; ..."); (6) izleyiciye yorum yaptıracak TEK görüş sorusu.
KAYNAKLAR: 2-5 RESMÎ kaynak; yalnızca kurum adı + kök alan adı (örn. {{"ad":"A101 – Kurumsal","alan":"a101.com.tr"}}). Alt sayfa URL'si UYDURMA.
ETİKETLER: 10-12 Türkçe arama terimi (marka adı, "<marka> neden", sektör, "tüketici hakları", "belgesel").
KAPAK: 'kapak_yazi' = {{"ust":"1 kelime (kırmızı etiket, örn. NEDEN)","alt":"1-2 kelime, en fazla 12 harf (dev yazı, örn. BİTİYOR?)"}}; 'kapak_gorsel' = İngilizce görsel promptu: konuyu tek bakışta anlatan TEK güçlü nesne/sahne, çerçevenin sağında, sol taraf karanlık ve boş; marka tabelası gerekiyorsa yazıyı birebir ver (örn. "store sign reading 'A101'").
'kanca' = kapakta da kullanılabilecek en fazla 3 kelimelik çarpıcı Türkçe ifade.
SADECE şu JSON'u döndür:
{{"baslik":"...","aciklama":"...","etiketler":["..."],"kanca":"...","kapak_yazi":{{"ust":"...","alt":"..."}},"kapak_gorsel":"...","kaynaklar":[{{"ad":"...","alan":"..."}}],"bolumler":[{{"baslik":"...","ozet":"..."}}]}}"""

BOLUM_PROMPT = """BAŞLIK: {baslik}
{ortak}

VİDEO PLANI:
{plan}

GÖREV: YALNIZCA {no}. bölümün seslendirme metnini yaz — "{bolum}" ({rol}).
Bu bölümde anlatılacaklar: {ozet}
UZUNLUK: yaklaşık {kelime} kelime (en az {asgari}).
{ozel}
Bölüm başlığını metne YAZMA; emoji ve madde işareti yok; düz, akıcı konuşma dili. Bölüm sonunda bir sonraki bölüme merak bırak ("ama hikâye burada bitmiyor" gibi), son bölüm hariç.
Metni 4-7 sahneye böl (sahne başı 20-35 kelime). Her sahne için:
- 'metin': o sahnenin Türkçe anlatım parçası (sahneler sırayla birleşince bölüm metni olur).
- 'gorsel_prompt': o an anlatılanı gösteren 15-30 kelimelik İNGİLİZCE, fotoğraf gerçekliğinde görsel üretim promptu: somut kişi, mekân, nesne, ışık, kamera açısı (örn. "long queue of shoppers outside a Turkish discount supermarket at 9am, morning light, wide shot"). Mekân TÜRKİYE: sahnede görünen tabela, fiyat etiketi, afiş ve ekran yazıları TÜRKÇE olsun ve tırnak içinde kısa verilsin (örn. "price tags reading '%50 İNDİRİM'", "shelf sign reading 'SON ÜRÜNLER'"); İngilizce yazı İSTEME. Marka mağazası gerekiyorsa tabeladaki yazıyı birebir ver ("store sign reading 'A101'"); logo/filigran isteme. Gerçek, tanınmış kişilerin yüzünü İSTEME (arkadan, uzaktan ya da ortamla anlat).
- 'arsiv': anlatılan olay geçmişteyse (kuruluş yılları, eski bir kriz) true, değilse false.
- 'gorsel': 2-4 kelimelik İngilizce stok anahtar kelimesi (yedek).
SADECE şu JSON'u döndür:
{{"sahneler":[{{"metin":"...","gorsel_prompt":"...","arsiv":false,"gorsel":"..."}}]}}"""

_YABANCI_ALFABE = re.compile(r"[\u0370-\u03FF\u0400-\u052F\u0590-\u08FF\u0E00-\u0E7F\u3000-\u9FFF\uAC00-\uD7AF]+")
_CLAUDE_KAPALI = False  # kredi/erişim hatası alınca bu koşuda Claude bir daha denenmez


def _llm_json(prompt, kontrol, etiket, yedek_kontrol=None):
    """Claude -> Gemini modelleri sırasıyla dener; JSON'u ayrıştırıp kontrol()'den
    geçen ilk yanıtı döndürür. kontrol(data) -> None (uygun) | hata metni.
    Hiçbiri geçmezse yedek_kontrol()'ü (daha gevşek) geçen ilk yanıt döner:
    birkaç kelime kısa kalan bir bölüm yüzünden tüm video düşmesin."""
    global _CLAUDE_KAPALI
    hatalar, yedek = [], None
    saglayicilar = []
    ckey = _claude_key()
    if ckey and not _CLAUDE_KAPALI:
        saglayicilar.append(("claude", lambda: _claude(prompt, ckey, max_tokens=8192)))
    gkey = _gemini_key()
    if gkey:
        for m in GEMINI_MODELS:
            saglayicilar.append((m, lambda m=m: _gemini_uzun(prompt, gkey, m)))
    for ad, fn in saglayicilar:
        for deneme in range(2):
            try:
                data = json.loads(_temizle(fn()))
                sorun = kontrol(data) if isinstance(data, dict) else "json nesne değil"
                if not sorun:
                    print(f"    {etiket}: {ad} ✓")
                    return data
                hatalar.append(f"{ad}#{deneme+1}: {sorun}")
                if yedek is None and yedek_kontrol and not yedek_kontrol(data):
                    yedek = (ad, data)
            except Exception as e:
                msg = str(e)
                hatalar.append(f"{ad}#{deneme+1}: {msg[:120]}")
                if ad == "claude" and ("credit" in msg or "401" in msg or "403" in msg):
                    _CLAUDE_KAPALI = True
                    print(f"    (Claude bu koşuda kapatıldı: {msg[:90]})")
                    break
                if "429" in msg:
                    time.sleep(20)
                elif "503" in msg:
                    time.sleep(10)  # model geçici olarak meşgul
    if yedek:
        print(f"    {etiket}: {yedek[0]} ✓ (hedefin altında, kabul edildi: {hatalar[-1][:60]})")
        return yedek[1]
    raise RuntimeError(f"{etiket} üretilemedi: " + " | ".join(hatalar[-6:]))


def uret_belgesel(baslik, not_=""):
    not_satiri = f"YAPIMCI NOTU (açı/odak): {not_}\n" if not_ else ""
    yapi = "\n".join(f"{i+1}) {ad}: {acik}" for i, (ad, _, acik) in enumerate(BELGESEL_YAPI))

    def plan_kontrol(d):
        b = d.get("bolumler") or []
        if len(b) < len(BELGESEL_YAPI) - 1:
            return f"bölüm sayısı {len(b)}"
        if not (d.get("kapak_yazi") or {}).get("alt"):
            return "kapak_yazi eksik"
        return None
    plan = _llm_json(PLAN_PROMPT.format(baslik=baslik, not_satiri=not_satiri, ortak=_ORTAK, yapi=yapi),
                     plan_kontrol, "Plan")
    bolumler = plan["bolumler"][:len(BELGESEL_YAPI)]
    plan_metni = "\n".join(f"{i+1}. {b.get('baslik','')}: {b.get('ozet','')}" for i, b in enumerate(bolumler))

    sahneler, bolum_isaret, onceki = [], [], ""
    for i, b in enumerate(bolumler):
        ad, kelime, _ = BELGESEL_YAPI[min(i, len(BELGESEL_YAPI) - 1)]
        asgari = int(kelime * 0.7)
        if i == 0:
            ozel = ('AÇILIŞ: Somut sahneyle başla, başlıktaki soruyu sor; ardından tam olarak şu cümleyi kur: '
                    '"Burası Tuzak Avcısı; hayatın içindeki tuzakları birlikte çözüyoruz." ve bu videoda neyi öğreneceğini söyle.')
        elif i == len(bolumler) - 1:
            ozel = (f'Önceki bölümün son cümlesi: "{onceki}" — buradan akıcı devam et. KAPANIŞ: 1. bölümdeki kişiye/vakaya geri dön, '
                    '"bir sonraki tuzağı kaçırmamak için abone ol" de ve izleyiciye görüş soran TEK bir soruyla bitir.')
        else:
            ozel = f'Önceki bölümün son cümlesi: "{onceki}" — buradan akıcı biçimde devam et; selamlama ya da tekrar yapma.'

        def bolum_kontrol(d, asgari=asgari):
            ss = [s for s in (d.get("sahneler") or []) if isinstance(s, dict) and (s.get("metin") or "").strip()]
            metin = " ".join(s["metin"] for s in ss)
            if len(metin.split()) < asgari:
                return f"kısa ({len(metin.split())} < {asgari})"
            if not _turkce_yeterli(metin):
                return "türkçe karakter eksik"
            return None
        d = _llm_json(BOLUM_PROMPT.format(baslik=baslik, ortak=_ORTAK, plan=plan_metni, no=i + 1,
                                          bolum=b.get("baslik", ""), rol=ad, ozet=b.get("ozet", ""),
                                          kelime=kelime, asgari=asgari, ozel=ozel),
                      bolum_kontrol, f"Bölüm {i+1}/{len(bolumler)}",
                      yedek_kontrol=lambda d, a=int(kelime * 0.45): bolum_kontrol(d, a))
        ss = [s for s in d["sahneler"] if isinstance(s, dict) and (s.get("metin") or "").strip()]
        for s_ in ss:  # model bazen Arapça/Kiril/CJK karakter sızdırıyor (seslendirmede bozulur)
            s_["metin"] = re.sub(r"\s{2,}", " ", _YABANCI_ALFABE.sub("", s_["metin"])).strip()
        bolum_isaret.append({"baslik": b.get("baslik", ""), "sahne": len(sahneler)})
        sahneler.extend(ss)
        onceki = ss[-1]["metin"].strip().split(". ")[-1][:200]
        time.sleep(2)  # ücretsiz katman dakika sınırına takılmamak için

    data = {k: plan.get(k) for k in ("baslik", "aciklama", "etiketler", "kanca",
                                      "kapak_yazi", "kapak_gorsel", "kaynaklar")}
    data["baslik"] = (data.get("baslik") or baslik).strip()
    data["sahneler"] = sahneler
    data["bolumler"] = bolum_isaret
    data["script"] = " ".join(s["metin"].strip() for s in sahneler)
    n = len(data["script"].split())
    if n < 1000:
        raise RuntimeError(f"Belgesel metni kısa kaldı ({n} kelime)")
    print(f"    Senaryo: {n} kelime, {len(sahneler)} sahne, {len(bolum_isaret)} bölüm")
    return data


_TR_OZEL = set("çğıöşüÇĞİÖŞÜ")  # Türkçe'ye özgü, ASCII karşılığı olmayan harfler

def _turkce_yeterli(metin):
    """Metnin gercekten Turkce karakter icerdigini dogrular.
    Diakritiksiz (ASCII'ye sadelestirilmis) uretimi yakalar: gercek bir
    ~400 kelimelik Turkce metin bu harfleri yogun icerir; sadelestirilmis
    metinde neredeyse hic bulunmaz. Kisa metinlerde kontrol atlanir."""
    s = metin or ""
    if len(s) < 200:
        return True  # kanca gibi cok kisa alanlar tek basina yaniltici olabilir
    ozel = sum(1 for c in s if c in _TR_OZEL)
    # Gercek Turkce anlatim ~%8-10 ozel harf icerir; tamamen ASCII ~%0.
    # Esik %3: hem tam hem KISMEN diakritiksiz (kelimelerin bir kismi "guclu",
    # "cocuk" gibi bozuk) metinleri reddeder -> TTS'te yabanci aksan olmaz.
    return ozel >= len(s) * 0.03


def _gemini_key():
    # once UZUN hatta OZEL anahtar (ayri kota); yoksa ortak GEMINI_KEY.
    for _ad in ("GEMINI_KEY_UZUN", "GEMINI_KEY"):
        k = os.environ.get(_ad, "").strip()
        if k: return k
    raw = os.environ.get("GEMINI_API_KEY", "").strip()
    if raw.startswith("{"):
        try:
            j = json.loads(raw)
            return (j.get("gemini") or j.get("google") or "").strip()
        except Exception:
            return ""
    return raw


def _yeterli(data, min_kelime):
    """Script var, sahneli, Türkçe karakterli ve hedef uzunlukta mı?
    Belgesel temasında ayrı 'script' alanı yok (çıktıyı yarıya indirir, JSON
    kesilmez): seslendirme metni sahne metinlerinin birleşimidir."""
    if not data.get("script") and data.get("sahneler"):
        data["script"] = " ".join((s.get("metin") or "").strip()
                                  for s in data["sahneler"] if isinstance(s, dict)).strip()
    sc = data.get("script") or ""
    if not (sc and data.get("sahneler")):
        return "bos yanit"
    if not _turkce_yeterli(sc):
        return "turkce karakter eksik"
    if len(sc.split()) < min_kelime:
        return f"kisa ({len(sc.split())} kelime < {min_kelime})"
    return None


def uret(baslik, tema="tuketici_belgesel", not_=""):
    if tema != "gizem":
        return uret_belgesel(baslik, not_)
    # Eski ~3 dk gizem hattı: tek istekte (kısa metin, sorun yok).
    min_kelime = 300
    prompt = UZUN_PROMPT.format(baslik=baslik)
    hatalar = []
    # 1) Anthropic Claude (en kaliteli/en tutarli Turkce) — birincil saglayici
    ckey = _claude_key()
    if ckey:
        for deneme in range(2):
            try:
                data = json.loads(_temizle(_claude(prompt, ckey, max_tokens=16000)))
                sorun = _yeterli(data, min_kelime)
                if not sorun:
                    print(f"    Senaryo: Anthropic Claude ({len(data['script'].split())} kelime)")
                    return data
                hatalar.append(f"claude#{deneme+1}: {sorun}")
                if deneme == 0 and sorun != "bos yanit":
                    continue
                break
            except Exception as e:
                msg = str(e)
                hatalar.append(f"claude#{deneme+1}: {msg[:90]}")
                if "429" in msg and deneme == 0:
                    time.sleep(15); continue
                break  # 401/404/diger -> Gemini'ye dus
    # 2) Gemini (yedek)
    key = _gemini_key()
    if key:
        for model in GEMINI_MODELS:
            for deneme in range(2):
                try:
                    data = json.loads(_temizle(_gemini_uzun(prompt, key, model)))
                    sorun = _yeterli(data, min_kelime)
                    if not sorun:
                        print(f"    Senaryo: Gemini ({model}, {len(data['script'].split())} kelime)")
                        return data
                    # Diakritiksiz (ASCII) ya da kisa uretim -> kabul etme, tekrar dene.
                    hatalar.append(f"{model}#{deneme+1}: {sorun}")
                    if deneme == 0 and sorun != "bos yanit":
                        continue  # ayni modelle bir kez daha dene
                    break         # sonraki modele gec
                except Exception as e:
                    msg = str(e)
                    hatalar.append(f"{model}#{deneme+1}: {msg[:90]}")
                    if "429" in msg and deneme == 0:
                        time.sleep(20); continue
                    break  # 404/diger -> bu modeli birak, sonrakine gec
    for ad, fn in (("poll_post", lambda: _poll_post(prompt)),
                   ("poll_get", lambda: _poll_get(prompt))):
        try:
            data = json.loads(_temizle(fn()))
            sorun = _yeterli(data, min_kelime)
            if not sorun:
                print(f"    Senaryo: {ad} (yedek)")
                return data
            hatalar.append(f"{ad}: {sorun}")
        except Exception as e:
            hatalar.append(f"{ad}: {str(e)[:90]}")
    raise RuntimeError("Uzun script uretilemedi: " + " | ".join(hatalar[:8]))


if __name__ == "__main__":
    import sys
    print(json.dumps(uret(sys.argv[1] if len(sys.argv) > 1 else "A101 Aldın Aldın Neden Hep Bitiyor?"),
                     ensure_ascii=False, indent=2))
