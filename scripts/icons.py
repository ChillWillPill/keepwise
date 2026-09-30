"""Builds every Keepwise icon from the owl-and-wallet logo (assets/logo-source.jpg).
The round emblem is cut out of the source, cleaned to pure white, then placed at each size the app needs."""
from PIL import Image, ImageDraw
import numpy as np, os, base64, io
ROOT = os.path.join(os.path.dirname(__file__), "..")
SRC = os.path.join(ROOT, "assets/logo-source.jpg")
WHITE, CREAM = (255, 255, 255), (243, 239, 230)

def emblem():
    """The round badge: teal ring with the owl inside, transparent outside the ring."""
    im = Image.open(SRC).convert("RGB")
    a = np.array(im).astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    teal = (g > 110) & (r < 80) & (b > 90) & (g - r > 60)
    ys, xs = np.where(teal[: int(a.shape[0] * 0.66)])
    cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    rad = max(xs.max() - xs.min(), ys.max() - ys.min()) / 2 + 6
    near_white = (r > 232) & (g > 232) & (b > 232)
    a[near_white] = 255  # remove JPEG speckle from the background
    im = Image.fromarray(a.astype("uint8"))
    box = (int(cx - rad), int(cy - rad), int(cx + rad), int(cy + rad))
    crop = im.crop(box).convert("RGBA")
    n = crop.size[0]
    big = n * 4
    mask = Image.new("L", (big, big), 0); ImageDraw.Draw(mask).ellipse([0, 0, big - 1, big - 1], fill=255)
    crop.putalpha(mask.resize((n, n), Image.LANCZOS))
    return crop

E = emblem()
def badge(px): return E.resize((px, px), Image.LANCZOS)
def square(size, frac, bg=WHITE, rounded=False):
    s = Image.new("RGBA", (size, size), bg + (255,))
    if rounded:
        m = Image.new("L", (size * 4, size * 4), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, size * 4 - 1, size * 4 - 1], radius=int(size * 4 * 0.22), fill=255)
        s.putalpha(m.resize((size, size), Image.LANCZOS))
    e = badge(int(size * frac)); o = (size - e.size[0]) // 2
    s.alpha_composite(e, (o, o))
    return s

os.makedirs(os.path.join(ROOT, "www/icons"), exist_ok=True)
for n in (192, 512): square(n, 0.9, rounded=True).save(os.path.join(ROOT, f"www/icons/icon-{n}.png"))
square(512, 0.72).save(os.path.join(ROOT, "www/icons/maskable-512.png"))       # inside the maskable safe zone
square(180, 0.9).convert("RGB").save(os.path.join(ROOT, "www/icons/apple-touch-icon.png"))
badge(64).save(os.path.join(ROOT, "www/icons/favicon-64.png"))
square(1024, 0.9).convert("RGB").save(os.path.join(ROOT, "assets/icon-only.png"))
fg = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0)); e = badge(640); fg.alpha_composite(e, ((1024 - 640) // 2,) * 2)
fg.save(os.path.join(ROOT, "assets/icon-foreground.png"))                        # Android adaptive icon, 66% safe zone
Image.new("RGB", (1024, 1024), WHITE).save(os.path.join(ROOT, "assets/icon-background.png"))
for name, bg in (("splash.png", CREAM), ("splash-dark.png", (20, 22, 19))):
    sp = Image.new("RGBA", (2732, 2732), bg + (255,)); b = badge(640); sp.alpha_composite(b, ((2732 - 640) // 2,) * 2)
    sp.convert("RGB").save(os.path.join(ROOT, "assets", name))
# the small header logo, embedded in the app so it also works offline and in the Claude preview
buf = io.BytesIO(); badge(96).save(buf, "PNG", optimize=True)
open(os.path.join(ROOT, "assets/logo-96.b64"), "w").write(base64.b64encode(buf.getvalue()).decode())
print("icons done, header logo", len(buf.getvalue()), "bytes")
