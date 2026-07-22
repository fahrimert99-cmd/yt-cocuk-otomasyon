# -*- coding: utf-8 -*-
"""4 alternatif Chirp3-HD sesiyle ayni metni uretir, repoya kaydeder."""
import os, json, base64, urllib.request, subprocess

def _keys():
    raw=(os.environ.get("GEMINI_API_KEY") or "").strip()
    try: return json.loads(raw)
    except Exception: return {}

KEY=_keys().get("google","")
METIN=("Kasada beklerken önündeki çikolata tesadüf değil. "
       "Tam iraden en zayıfken oraya konur. Kasada neden çikolata var? "
       "Çünkü orası en kârlı köşedir.")
SESLER=["tr-TR-Chirp3-HD-Charon","tr-TR-Chirp3-HD-Rasalgethi",
        "tr-TR-Chirp3-HD-Sadaltager","tr-TR-Chirp3-HD-Alnilam"]

for ses in SESLER:
    body={"input":{"text":METIN},
          "voice":{"languageCode":"tr-TR","name":ses},
          "audioConfig":{"audioEncoding":"MP3","speakingRate":1.0}}
    url=f"https://texttospeech.googleapis.com/v1beta1/text:synthesize?key={KEY}"
    req=urllib.request.Request(url,data=json.dumps(body).encode(),
        headers={"Content-Type":"application/json","User-Agent":"Mozilla/5.0 (compatible; ytbot/1.0)"})
    try:
        with urllib.request.urlopen(req,timeout=120) as r:
            d=json.loads(r.read().decode())
        ad=ses.split("-")[-1].lower()
        with open(f"ses_{ad}.mp3","wb") as f:
            f.write(base64.b64decode(d["audioContent"]))
        print(f"OK {ses}")
    except Exception as e:
        print(f"HATA {ses}: {str(e)[:150]}")

# repoya push
subprocess.run(["git","config","user.email","bot@x"],check=False)
subprocess.run(["git","config","user.name","bot"],check=False)
subprocess.run(["git","add","ses_*.mp3"],check=False)
subprocess.run(["git","commit","-m","ses ornekleri"],check=False)
subprocess.run(["git","push"],check=False)
