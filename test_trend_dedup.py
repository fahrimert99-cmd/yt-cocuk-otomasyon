import trend


def test_genel_kategori_kesisimi_farkli_alt_konulari_elemez():
    mevcut = ["ÜCRETSİZ KARGO EŞİĞİ NEDEN VAR? 🚚"]
    yeni = "KARGODAKİ GİZLİ ÜCRET: ÖDEME EKRANI NASIL DEĞİŞİR? 💳"
    assert trend._konu_cakismasi(yeni, mevcut) is None


def test_ozel_koklu_iki_baslik_tekrar_sayilir():
    mevcut = ["SİNEMA MISIRI NEDEN O KADAR PAHALI? 🍿"]
    yeni = "SİNEMADA MISIR NEDEN PAHALI? 🍿"
    assert trend._konu_cakismasi(yeni, mevcut) == mevcut[0]


def test_uc_genel_kok_guculu_tekrar_sinyalidir():
    mevcut = ["MARKETTE ÖDEME KARTI ÜCRET TUZAĞI! 🛒"]
    yeni = "MARKETTE ÖDEME KARTI GİZLİ ÜCRET NASIL ÇALIŞIR? 💳"
    assert trend._konu_cakismasi(yeni, mevcut) == mevcut[0]


if __name__ == "__main__":
    test_genel_kategori_kesisimi_farkli_alt_konulari_elemez()
    test_ozel_koklu_iki_baslik_tekrar_sayilir()
    test_uc_genel_kok_guculu_tekrar_sinyalidir()
    print("trend dedup testleri: OK")
