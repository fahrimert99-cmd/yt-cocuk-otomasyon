import hashlib
from yorum_at import yorum_metni_uret


def test_trend_yorumu_korunur():
    veri = {"baslik": "SAHTE GERİ SAYIM SAYACI!", "yorum": "Bu sayaçta seni en çok şaşırtan ayrıntı neydi?"}
    assert yorum_metni_uret(veri) == veri["yorum"]


def test_eksik_yorum_videoya_ozgu_fallback_uretir():
    veri = {"baslik": "ÜCRETSİZ KARGO EŞİĞİ NEDEN VAR? 🚚"}
    yorum = yorum_metni_uret(veri)
    assert "ÜCRETSİZ KARGO EŞİĞİ NEDEN VAR" in yorum
    assert "http" not in yorum.lower()
    assert len(yorum) <= 280


def test_uzun_ve_linkli_yorum_fallbacka_duser():
    veri = {"baslik": "ÖDEME EKRANI", "yorum": "https://example.com " + "x" * 300}
    yorum = yorum_metni_uret(veri)
    assert yorum.startswith("ÖDEME EKRANI hakkında")


if __name__ == "__main__":
    test_trend_yorumu_korunur()
    test_eksik_yorum_videoya_ozgu_fallback_uretir()
    test_uzun_ve_linkli_yorum_fallbacka_duser()
    print("yorum entegrasyonu testleri: OK")
