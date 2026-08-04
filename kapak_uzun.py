#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Uzun (yatay 16:9) icin PROFESYONEL tarz kapak (1280x720): dramatik zemin + parlak
kirmizi 3D 'play' ogeleri + isik parlamasi + dev iki-renkli (beyaz/sari) yazi."""
import os, re, math, subprocess
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
import PIL.ImageStat as S

W, H = 1280, 720
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SARI=(255,214,0); BEYAZ=(255,255,255)
# yaziyi ikiye bolmek icin 'vurgu' kelimeleri (sari olacak)
VURGU=["TUZA","YALAN","HİL","KANDIR","ALDAT","TEHLİK","DİKKAT","GERÇEK","SAKIN","SOY",
       "PARA","BEDAVA","ÜCRETSİZ","DUR","KAND","ÇALIYOR","SOYUYOR","HİLE","YALANI"]

def _upper(s):
    return s.translate(str.maketrans({"i":"İ","ı":"I","ş":"Ş","ğ":"Ğ","ü":"Ü","ö":"Ö","ç":"Ç"})).upper()

def _sure(v):
    r=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nokey=1:noprint_wrappers=1",v],capture_output=True,text=True)
    try: return float(r.stdout.strip())
    except: return 5.0

def _kare(video, frame):
    best=None; bs=-1
    for p in (0.2,0.35,0.5,0.65,0.8):
        f=f"/tmp/_k{int(p*100)}.jpg"
        subprocess.run(["ffmpeg","-y","-ss",f"{max(0.4,_sure(video)*p):.2f}","-i",video,"-frames:v","1",f],capture_output=True)
        try:
            im=Image.open(f).convert("RGB"); m=S.Stat(im.convert("L")).mean[0]; sat=S.Stat(im.convert("HSV")).mean[1]
            sc=sat*0.8+(70-abs(m-130))
            if sc>bs: bs=sc; best=f
        except: pass
    if best: subprocess.run(["cp",best,frame])
    return os.path.exists(frame)

def _play_button(size=190):
    """parlak kirmizi 3D play butonu (RGBA)."""
    im=Image.new("RGBA",(size,size),(0,0,0,0)); d=ImageDraw.Draw(im)
    r=int(size*0.22)
    # govde: kirmizi dikey degrade
    for y in range(size):
        f=y/size; col=(int(235-70*f),int(30-15*f),int(40-20*f),255)
        d.line([(0,y),(size,y)],fill=col)
    # yuvarlak kose maskesi
    mask=Image.new("L",(size,size),0); md=ImageDraw.Draw(mask)
    md.rounded_rectangle([0,0,size-1,size-1],radius=r,fill=255)
    im.putalpha(mask)
    d=ImageDraw.Draw(im)
    # ust parlak highlight
    hi=Image.new("RGBA",(size,size),(0,0,0,0)); hd=ImageDraw.Draw(hi)
    hd.rounded_rectangle([int(size*0.1),int(size*0.08),int(size*0.9),int(size*0.4)],radius=r,fill=(255,255,255,60))
    hi=hi.filter(ImageFilter.GaussianBlur(8)); im=Image.alpha_composite(im,hi)
    d=ImageDraw.Draw(im)
    # beyaz play ucgeni
    cx,cy=size*0.54,size*0.5; s=size*0.26
    d.polygon([(cx-s*0.7,cy-s),(cx-s*0.7,cy+s),(cx+s,cy)],fill=(255,255,255,255))
    # ince koyu kenar
    d.rounded_rectangle([1,1,size-2,size-2],radius=r,outline=(120,0,10,180),width=3)
    return im

def _glow_paste(base, prop, xy, angle):
    p=prop.rotate(angle,expand=True,resample=Image.BICUBIC)
    # kirmizi parlama
    glow=Image.new("RGBA",base.size,(0,0,0,0))
    gp=p.split()[3].point(lambda a:int(a*0.9))
    tint=Image.new("RGBA",p.size,(255,40,40,0)); tint.putalpha(gp)
    glow.paste(tint,(xy[0]-p.width//2,xy[1]-p.height//2),tint)
    glow=glow.filter(ImageFilter.GaussianBlur(22))
    base.alpha_composite(glow)
    base.alpha_composite(p,(xy[0]-p.width//2,xy[1]-p.height//2))

def kapak_uret(video_path, baslik, cikti="output/uzun_kapak.jpg"):
    os.makedirs(os.path.dirname(cikti) or ".", exist_ok=True)
    frame="/tmp/_ku.jpg"
    if not _kare(video_path,frame): Image.new("RGB",(W,H),(14,10,18)).save(frame)
    try: bg=Image.open(frame).convert("RGB")
    except: bg=Image.new("RGB",(W,H),(14,10,18))
    sc=max(W/bg.width,H/bg.height); bg=bg.resize((int(bg.width*sc),int(bg.height*sc)),Image.LANCZOS)
    l=(bg.width-W)//2; t=(bg.height-H)//2; bg=bg.crop((l,t,l+W,t+H))
    # DRAMATIK zemin: koyu + canli + guclu vignette
    bg=ImageEnhance.Color(bg).enhance(1.5); bg=ImageEnhance.Contrast(bg).enhance(1.25)
    bg=ImageEnhance.Brightness(bg).enhance(0.62)
    vig=Image.new("L",(W,H),0); ImageDraw.Draw(vig).ellipse([-120,-360,W+120,H+220],fill=255)
    vig=vig.filter(ImageFilter.GaussianBlur(190))
    bg=Image.composite(bg,ImageEnhance.Brightness(bg).enhance(0.4),vig)
    base=bg.convert("RGBA")
    # merkez sicak isik parlamasi
    glow=Image.new("RGBA",(W,H),(0,0,0,0)); ImageDraw.Draw(glow).ellipse([W*0.28,H*0.02,W*0.72,H*0.5],fill=(255,90,40,70))
    glow=glow.filter(ImageFilter.GaussianBlur(120)); base=Image.alpha_composite(base,glow)

    # 3D PLAY OGELERI (kose/kenarlar, hafif acili) — referanstaki gibi
    pb=_play_button(200)
    _glow_paste(base,pb,(120,150),18)
    _glow_paste(base,pb,(W-120,150),-16)
    _glow_paste(base,_play_button(140),(90,H-250),-10)
    _glow_paste(base,_play_button(140),(W-95,H-250),12)
    d=ImageDraw.Draw(base,"RGBA")

    # ---- DEV IKI-RENKLI YAZI (alt) ----
    metin=_upper(re.sub(r"[^\w\sğüşiöçİĞÜŞÖÇ?!.,'-]","",baslik,flags=re.UNICODE).strip())
    kel=metin.split()
    for fs in (150,136,122,110,98):
        font=ImageFont.truetype(FB,fs); maxw=W-150; sat=[]; cur=""
        for k in kel:
            if d.textlength((cur+" "+k).strip(),font=font)<=maxw: cur=(cur+" "+k).strip()
            else: sat.append(cur); cur=k
        if cur: sat.append(cur)
        if len(sat)<=3: break
    lh=int(fs*1.02); blok=lh*len(sat); ty=H-blok-40
    def ciz(x,y,word,renk,font,o):
        for dx in range(-o,o+1,2):
            for dy in range(-o,o+1,2):
                d.text((x+dx,y+dy),word,font=font,fill=(0,0,0,255))
        d.text((x,y),word,font=font,fill=renk)
    for ln in sat:
        w=d.textlength(ln,font=font); tx=(W-w)//2; o=max(6,fs//11); cx=tx
        for word in ln.split():
            renk=SARI if any(word.startswith(v) or v in word for v in VURGU) else BEYAZ
            ciz(cx,ty,word,renk,font,o); cx+=d.textlength(word+" ",font=font)
        ty+=lh

    base.convert("RGB").save(cikti,quality=90)
    return cikti

if __name__=="__main__":
    import sys
    print(kapak_uret(sys.argv[1] if len(sys.argv)>1 else "in.mp4",
                     sys.argv[2] if len(sys.argv)>2 else "OYUNLARDAKİ SATIN ALMA TUZAĞI"))
