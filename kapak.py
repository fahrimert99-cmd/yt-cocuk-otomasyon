#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shorts (dikey 9:16, 1080x1920) icin CARPICI kapak: dramatik zemin + parlak kirmizi
3D 'play' ogeleri + isik + dev iki-renkli (beyaz/sari) yazi. kapak.py yerine gecebilir."""
import os, re, math, subprocess
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
import PIL.ImageStat as S
W,H=1080,1920
FB="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SARI=(255,214,0); BEYAZ=(255,255,255)
VURGU=["TUZA","YALAN","HİL","KANDIR","ALDAT","TEHLİK","DİKKAT","GERÇEK","SAKIN","SOY",
       "PARA","BEDAVA","ÜCRETSİZ","DUR","KAND","ÇALIYOR","SOYUYOR","YALANI","HİLE"]
def _up(s): return s.translate(str.maketrans({"i":"İ","ı":"I","ş":"Ş","ğ":"Ğ","ü":"Ü","ö":"Ö","ç":"Ç"})).upper()
def _sure(v):
    r=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nokey=1:noprint_wrappers=1",v],capture_output=True,text=True)
    try: return float(r.stdout.strip())
    except: return 5.0
def _kare(video,frame):
    best=None;bs=-1
    for p in (0.2,0.4,0.6,0.8):
        f=f"/tmp/_s{int(p*100)}.jpg"
        subprocess.run(["ffmpeg","-y","-ss",f"{max(0.4,_sure(video)*p):.2f}","-i",video,"-frames:v","1",f],capture_output=True)
        try:
            im=Image.open(f).convert("RGB");m=S.Stat(im.convert("L")).mean[0];sat=S.Stat(im.convert("HSV")).mean[1]
            sc=sat*0.8+(70-abs(m-130))
            if sc>bs:bs=sc;best=f
        except:pass
    if best:subprocess.run(["cp",best,frame])
    return os.path.exists(frame)
def _play(size):
    im=Image.new("RGBA",(size,size),(0,0,0,0));d=ImageDraw.Draw(im);r=int(size*0.22)
    for y in range(size):
        f=y/size;d.line([(0,y),(size,y)],fill=(int(235-70*f),int(30-15*f),int(40-20*f),255))
    mask=Image.new("L",(size,size),0);ImageDraw.Draw(mask).rounded_rectangle([0,0,size-1,size-1],radius=r,fill=255)
    im.putalpha(mask);d=ImageDraw.Draw(im)
    hi=Image.new("RGBA",(size,size),(0,0,0,0));ImageDraw.Draw(hi).rounded_rectangle([int(size*0.1),int(size*0.08),int(size*0.9),int(size*0.4)],radius=r,fill=(255,255,255,60))
    im=Image.alpha_composite(im,hi.filter(ImageFilter.GaussianBlur(8)));d=ImageDraw.Draw(im)
    cx,cy,sp=size*0.54,size*0.5,size*0.26
    d.polygon([(cx-sp*0.7,cy-sp),(cx-sp*0.7,cy+sp),(cx+sp,cy)],fill=(255,255,255,255))
    d.rounded_rectangle([1,1,size-2,size-2],radius=r,outline=(120,0,10,180),width=3);return im
def _paste(base,prop,xy,ang):
    p=prop.rotate(ang,expand=True,resample=Image.BICUBIC)
    glow=Image.new("RGBA",base.size,(0,0,0,0));a=p.split()[3].point(lambda v:int(v*0.9))
    t=Image.new("RGBA",p.size,(255,40,40,0));t.putalpha(a)
    glow.paste(t,(xy[0]-p.width//2,xy[1]-p.height//2),t)
    base.alpha_composite(glow.filter(ImageFilter.GaussianBlur(24)))
    base.alpha_composite(p,(xy[0]-p.width//2,xy[1]-p.height//2))
def kapak_uret(video_path,baslik,cikti="output/kapak.jpg"):
    os.makedirs(os.path.dirname(cikti) or ".",exist_ok=True)
    fr="/tmp/_sp.jpg"
    if not _kare(video_path,fr): Image.new("RGB",(W,H),(14,10,18)).save(fr)
    try: bg=Image.open(fr).convert("RGB")
    except: bg=Image.new("RGB",(W,H),(14,10,18))
    sc=max(W/bg.width,H/bg.height);bg=bg.resize((int(bg.width*sc),int(bg.height*sc)),Image.LANCZOS)
    l=(bg.width-W)//2;t=(bg.height-H)//2;bg=bg.crop((l,t,l+W,t+H))
    bg=ImageEnhance.Color(bg).enhance(1.5);bg=ImageEnhance.Contrast(bg).enhance(1.24);bg=ImageEnhance.Brightness(bg).enhance(0.66)
    vig=Image.new("L",(W,H),0);ImageDraw.Draw(vig).ellipse([-160,-200,W+160,H+200],fill=255)
    bg=Image.composite(bg,ImageEnhance.Brightness(bg).enhance(0.4),vig.filter(ImageFilter.GaussianBlur(220)))
    base=bg.convert("RGBA")
    glow=Image.new("RGBA",(W,H),(0,0,0,0));ImageDraw.Draw(glow).ellipse([W*0.2,H*0.28,W*0.8,H*0.62],fill=(255,90,40,60))
    base=Image.alpha_composite(base,glow.filter(ImageFilter.GaussianBlur(150)))
    # play ogeleri (kose)
    pb=_play(190)
    _paste(base,pb,(150,240),16);_paste(base,pb,(W-150,240),-15)
    _paste(base,_play(150),(120,H-360),-12);_paste(base,_play(150),(W-120,H-360),12)
    d=ImageDraw.Draw(base,"RGBA")
    metin=_up(re.sub(r"[^\w\sğüşiöçİĞÜŞÖÇ?!.,'-]","",baslik,flags=re.UNICODE).strip());kel=metin.split()
    for fs in (170,152,136,120,108):
        font=ImageFont.truetype(FB,fs);maxw=W-120;sat=[];cur=""
        for k in kel:
            if d.textlength((cur+" "+k).strip(),font=font)<=maxw:cur=(cur+" "+k).strip()
            else:sat.append(cur);cur=k
        if cur:sat.append(cur)
        if len(sat)<=4:break
    lh=int(fs*1.04);blok=lh*len(sat);ty=int(H*0.52)-blok//2
    for ln in sat:
        w=d.textlength(ln,font=font);tx=(W-w)//2;o=max(6,fs//11);cx=tx
        for dx in range(-o,o+1,2):
            for dy in range(-o,o+1,2): d.text((tx+dx,ty+dy),ln,font=font,fill=(0,0,0,255))
        for word in ln.split():
            renk=SARI if any(word.startswith(v) or v in word for v in VURGU) else BEYAZ
            d.text((cx,ty),word,font=font,fill=renk);cx+=d.textlength(word+" ",font=font)
        ty+=lh
    for i in range(8): d.rectangle([i,i,W-1-i,H-1-i],outline=(210,20,30))
    base.convert("RGB").save(cikti,quality=90);return cikti
if __name__=="__main__":
    import sys
    print(kapak_uret(sys.argv[1] if len(sys.argv)>1 else "in.mp4", sys.argv[2] if len(sys.argv)>2 else "OYUNLARDAKİ SATIN ALMA TUZAĞI"))
