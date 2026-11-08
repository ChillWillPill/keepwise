"""Shrink the Android icon and splash PNGs (256-colour palettes) after make_icons.js. Keeps the Play bundle small.
Run from the repo root: python3 scripts/icons/shrink.py"""
from PIL import Image
import glob, os
for f in glob.glob("android/app/src/main/res/**/*.png", recursive=True):
    a = os.path.getsize(f); im = Image.open(f)
    if im.mode not in ("RGBA", "RGB"): im = im.convert("RGBA")
    q = im.quantize(colors=256, method=Image.Quantize.FASTOCTREE) if im.mode == "RGBA" else im.quantize(colors=256)
    q.save(f + ".tmp", format="PNG", optimize=True)
    if os.path.getsize(f + ".tmp") < a: os.replace(f + ".tmp", f)
    else: os.remove(f + ".tmp")
