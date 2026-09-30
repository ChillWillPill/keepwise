"""Draws the Keepwise icon (green rounded square, white drop) at every size the app needs."""
from PIL import Image, ImageDraw
import os
OUT = os.path.join(os.path.dirname(__file__), "..")
GREEN, CREAM = (27, 104, 67), (243, 239, 230)
def draw(size, maskable=False, rounded=True):
    s = size * 4  # supersample
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0) if rounded else GREEN + (255,))
    d = ImageDraw.Draw(img)
    if rounded and not maskable: d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=GREEN)
    else: d.rectangle([0, 0, s, s], fill=GREEN)
    k = 0.62 if maskable else 0.78  # keep the drop inside the maskable safe zone
    cx, cy, r = s / 2, s * 0.56, s * 0.2 * k / 0.78
    top = cy - r * 2.05
    d.polygon([(cx, top), (cx - r * 0.93, cy - r * 0.35), (cx + r * 0.93, cy - r * 0.35)], fill="white")
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill="white")
    rr = r * 0.42
    d.ellipse([cx - rr, cy - rr + r * 0.1, cx + rr, cy + rr + r * 0.1], fill=GREEN)
    return img.resize((size, size), Image.LANCZOS)
os.makedirs(os.path.join(OUT, "www/icons"), exist_ok=True)
for n in (192, 512): draw(n).save(os.path.join(OUT, f"www/icons/icon-{n}.png"))
draw(512, maskable=True).save(os.path.join(OUT, "www/icons/maskable-512.png"))
draw(180, rounded=False).convert("RGB").save(os.path.join(OUT, "www/icons/apple-touch-icon.png"))
draw(1024, rounded=False).convert("RGB").save(os.path.join(OUT, "assets/icon-only.png"))
fg = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0)); fg.paste(draw(1024, maskable=True), (0, 0))
fg.save(os.path.join(OUT, "assets/icon-foreground.png"))
Image.new("RGB", (1024, 1024), GREEN).save(os.path.join(OUT, "assets/icon-background.png"))
sp = Image.new("RGB", (2732, 2732), CREAM); ic = draw(600); sp.paste(ic, ((2732 - 600) // 2, (2732 - 600) // 2), ic)
sp.save(os.path.join(OUT, "assets/splash.png")); sp.save(os.path.join(OUT, "assets/splash-dark.png"))
print("icons done")
