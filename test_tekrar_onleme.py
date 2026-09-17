import otomasyon


def test_ayni_konu_farkli_baslikla_yakalanir():
    eski = "SİNEMA MISIRI NEDEN O KADAR PAHALI? 🍿"
    yeni = "SİNEMADA MISIR NEDEN PAHALI? 🍿"
    assert otomasyon._konu_tekrari(yeni, {eski}) == eski


def test_farkli_konu_reddedilmez():
    eski = "SİNEMA MISIRI NEDEN O KADAR PAHALI? 🍿"
    yeni = "KREDİ KARTI TAKSİT TUZAĞI! 💳"
    assert otomasyon._konu_tekrari(yeni, {eski}) is None


def test_baslik_ayniysa_kok_sayisi_az_olsa_da_normalkontrol_disinda_kalir():
    assert otomasyon._konu_tekrari("KASA!", {"KASA!"}) is None


if __name__ == "__main__":
    test_ayni_konu_farkli_baslikla_yakalanir()
    test_farkli_konu_reddedilmez()
    test_baslik_ayniysa_kok_sayisi_az_olsa_da_normalkontrol_disinda_kalir()
    print("tekrar onleme testleri: OK")
