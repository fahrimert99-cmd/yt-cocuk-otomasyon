import json
import unicodedata

TERIMLER = (
    "market", "fiyat", "indirim", "ödeme", "ücret", "alışveriş", "ürün",
    "mağaza", "reyon", "raf", "sepet", "kasa", "restoran", "menü",
    "büfe", "sinema", "kart", "kredi", "banka", "faiz", "taksit",
    "kampanya", "kupon", "abonelik", "üyelik", "iade", "kargo", "garanti",
    "otopark", "kuaför", "berber", "uygulama", "site", "çerez", "wifi",
    "internet", "reklam", "para", "satış", "hizmet", "sözleşme", "bedava",
    "ücretsiz", "son iki",
)
ZAYIF = ("müzik", "koku", "sağa", "yön", "hız", "kokunun")
DOGRUDAN = (
    "fiyat", "indirim", "ücret", "ödeme", "para", "ürün", "market", "reyon",
    "raf", "sepet", "kasa", "kart", "kredi", "banka", "taksit", "kampanya",
    "abonelik", "üyelik", "iade", "kargo", "garanti", "menü", "gizli tuzak",
    "ekstra", "bedava", "ücretsiz", "son iki", "sınırlı", "çerez",
)

def uygun(s):
    def norm(v):
        return unicodedata.normalize("NFC", str(v)).replace("İ", "I").replace("ı", "i").lower()
    metin = norm(" ".join(str(s.get(k, "")) for k in ("baslik", "aciklama", "script")))
    if not any(norm(t) in metin for t in TERIMLER):
        return False
    baslik = norm(s.get("baslik", ""))
    return not any(norm(t) in baslik for t in ZAYIF) or any(norm(t) in baslik for t in DOGRUDAN)

x = json.load(open("senaryolar.json", encoding="utf-8-sig"))
y = [s for s in x if s.get("tema", "tuzak") == "tuzak" and uygun(s)]
bad = [s for s in x if s.get("tema", "tuzak") == "tuzak" and not uygun(s)]
print(f"uygun_tuzak={len(y)}")
print(f"elenen_konu_disi={len(bad)}")
print("örnek_sıradaki:")
for s in y[:8]:
    print("-", s.get("baslik"))
print("elenenler:")
for s in bad:
    print("-", s.get("baslik"))
assert y
assert all(uygun(s) for s in y)
