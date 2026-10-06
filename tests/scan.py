"""Build synthetic 'scanned' documents: text rendered to an image (optionally noisy/rotated), wrapped in an image-only PDF."""
import io
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

FONT_CANDIDATES = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]


def _font(size):
    for p in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def render(text: str, noise: float = 0.0, rotate: float = 0.0, size: int = 34) -> Image.Image:
    img = Image.new("L", (1650, 2340), 255)  # A4 @ 200 dpi
    d = ImageDraw.Draw(img)
    y = 150
    for line in text.splitlines():
        d.text((120, y), line, fill=0, font=_font(size))
        y += size + 22
    if rotate:
        img = img.rotate(rotate, expand=False, fillcolor=255)
    if noise:
        rnd = random.Random(1)
        px = img.load()
        for _ in range(int(noise * 1650 * 2340)):
            px[rnd.randrange(1650), rnd.randrange(2340)] = rnd.choice([0, 255])
        img = img.filter(ImageFilter.GaussianBlur(0.8))
    return img


def scanned_pdf(pages: list[str], **kw) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for t in pages:
        c.drawImage(ImageReader(render(t, **kw)), 0, 0, width=A4[0], height=A4[1])
        c.showPage()
    c.save()
    return buf.getvalue()


def png(text: str, **kw) -> bytes:
    b = io.BytesIO()
    render(text, **kw).save(b, "PNG")
    return b.getvalue()
