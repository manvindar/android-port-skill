#!/usr/bin/env python3
"""Fit docbt/GeminiBootAnimation (MIT, Pixel 10 Gemini animation, 1080x2340) to the TB-X606V panel (1200x1920).
Frames are scaled to the panel height, centred on black, reduced to a 128-colour palette (13 MB instead of 57 MB; black background, no visible banding).
usage: make_gemini_fit.py ORIGINAL.zip OUT.zip   (needs Pillow)"""
import io, os, re, sys, zipfile
from PIL import Image
src, dst = sys.argv[1:3]
zin = zipfile.ZipFile(src); S = 1920 / 2340; w = round(1080 * S)
zout = zipfile.ZipFile(dst, 'w', zipfile.ZIP_STORED)    # bootanimation requires stored entries
for zi in zin.infolist():
    if zi.is_dir(): continue
    data = zin.read(zi.filename)
    if zi.filename == 'desc.txt':
        data = data.decode().replace('1080 2340', '1200 1920').encode()
    elif zi.filename.endswith('.png'):
        im = Image.open(io.BytesIO(data)).convert('RGBA').resize((w, 1920), Image.LANCZOS)
        bg = Image.new('RGBA', (1200, 1920), (0, 0, 0, 255)); bg.alpha_composite(im, ((1200 - w) // 2, 0))
        q = bg.convert('RGB').quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
        b = io.BytesIO(); q.save(b, 'PNG', optimize=True); data = b.getvalue()
    zout.writestr(zipfile.ZipInfo(zi.filename, (2026, 1, 1, 0, 0, 0)), data)
zout.close(); print('wrote', dst, os.path.getsize(dst))
