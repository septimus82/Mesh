"""Contact sheet: sheet.py OUT.png COLS SCALE label=path [label=path ...] (labels drawn above each tile)."""
import sys
from PIL import Image, ImageDraw, ImageFont

out, cols, scale = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
items = [a.split("=", 1) for a in sys.argv[4:]]
imgs = [(lab, Image.open(p).convert("RGB")) for lab, p in items]
w, h = int(imgs[0][1].width * scale), int(imgs[0][1].height * scale)
pad = 22
rows = (len(imgs) + cols - 1) // cols
sheet = Image.new("RGB", (cols * w, rows * (h + pad)), (24, 24, 24))
d = ImageDraw.Draw(sheet)
try:
    font = ImageFont.truetype("arial.ttf", 15)
except OSError:
    font = ImageFont.load_default()
for i, (lab, im) in enumerate(imgs):
    x, y = (i % cols) * w, (i // cols) * (h + pad)
    sheet.paste(im.resize((w, h), Image.NEAREST if scale >= 1 else Image.LANCZOS), (x, y + pad))
    d.text((x + 6, y + 3), lab, fill=(235, 235, 235), font=font)
sheet.save(out)
print(out, sheet.size)
