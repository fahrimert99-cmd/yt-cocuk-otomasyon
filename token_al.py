#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TEK SEFERLİK — YouTube refresh token alma yardımcısı (kendi bilgisayarınızda çalıştırın).

1) Google Cloud Console'da bir proje açın, "YouTube Data API v3"ü VE
   "YouTube Analytics API"yi (youtubeanalytics.googleapis.com) etkinleştirin.
2) OAuth istemcisi (Masaüstü / Desktop app) oluşturup client_secret.json indirin,
   bu dosyanın yanına koyun.
3) pip install google-auth-oauthlib
4) python3 token_al.py
Çıkan CLIENT_ID / CLIENT_SECRET / REFRESH_TOKEN değerlerini GitHub Secrets'a ekleyin.

NOT: Analytics (retention/CTR) için aşağıdaki yt-analytics.readonly scope'u
eklidir. Scope değişince ESKİ refresh token geçersiz kalır — bu betiği yeniden
çalıştırıp YT_REFRESH_TOKEN secret'ını YENİ değerle güncelleyin.
"""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.force-ssl",       # yükleme + yorum (mevcut)
    "https://www.googleapis.com/auth/yt-analytics.readonly",   # retention/CTR raporları
]

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

print("\n==== BU 3 DEĞERİ GİTHUB SECRETS'A EKLE ====")
print("YT_CLIENT_ID     =", creds.client_id)
print("YT_CLIENT_SECRET =", creds.client_secret)
print("YT_REFRESH_TOKEN =", creds.refresh_token)
