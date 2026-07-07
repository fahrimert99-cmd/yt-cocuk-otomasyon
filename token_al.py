#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TEK SEFERLİK — YouTube refresh token alma yardımcısı (kendi bilgisayarınızda çalıştırın).

1) Google Cloud Console'da bir proje açın, "YouTube Data API v3"ü etkinleştirin.
2) OAuth istemcisi (Masaüstü / Desktop app) oluşturup client_secret.json indirin,
   bu dosyanın yanına koyun.
3) pip install google-auth-oauthlib
4) python3 token_al.py
Çıkan CLIENT_ID / CLIENT_SECRET / REFRESH_TOKEN değerlerini GitHub Secrets'a ekleyin.
"""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

print("\n==== BU 3 DEĞERİ GİTHUB SECRETS'A EKLE ====")
print("YT_CLIENT_ID     =", creds.client_id)
print("YT_CLIENT_SECRET =", creds.client_secret)
print("YT_REFRESH_TOKEN =", creds.refresh_token)
