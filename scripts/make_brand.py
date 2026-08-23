"""竹梅品牌資產產生器 — 一支腳本產出全套 logo／og 圖，設計系統單一來源。

設計系統（2026-08-22 定版）：
  底色一律黑（網站深色 canvas #000）、字型一律 Noto Sans TC Bold、
  竹＝交大藍漸層、梅＝清大紫漸層（同 site.css 的 chumei-bamboo/plum tokens）。

字型不進 git（26MB）；缺檔時先下載：
  curl -sL -o state/fonts/NotoSansTC-Bold.otf \
    https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Bold.otf

產出（site/assets/…）：
  brand/logo-mark-{16,32,48,64,256,1024}.png   竹梅雙字（favicon 等）
  brand/logo-square-{32,64,180,192,256,512,1024}.png 竹梅＋活動觀測站副標（192/512 兼 PWA icon）
  brand/logo-bot-{192,512,1024}.png            圓形頭貼安全版（Telegram/LINE 頭貼；192/512 兼 PWA maskable icon）
  brand/logo-chat-{512,1024}.png               對話泡泡版（bot 識別）
  og-default.png                               1200×630 社群分享圖

用法：.venv/bin/python scripts/make_brand.py
"""

from PIL import Image, ImageDraw, ImageFont

from chumei_lib import ROOT

FONT_PATH = ROOT / "state" / "fonts" / "NotoSansTC-Bold.otf"
BRAND_DIR = ROOT / "site" / "assets" / "brand"

BG = "#000000"
WHITE = "#F5F7FF"
MUTED = "#9EA8BF"
# 竹＝藍、梅＝紫；亮→深的縱向漸層，取 tokens 的 blue-400→500、plum-strong(dark)→(light)
GRAD_CHU = ("#5A78FF", "#2462FF")
GRAD_MEI = ("#C069DD", "#8E24AA")


def font(size):
    return ImageFont.truetype(str(FONT_PATH), size)


def _lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _hex(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def gradient_char(ch, fnt, c_top, c_bottom):
    """單字渲染成縱向漸層色塊（以字形當遮罩）。回 (RGBA image, advance)。"""
    bbox = fnt.getbbox(ch)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((-bbox[0], -bbox[1]), ch, font=fnt, fill=255)
    grad = Image.new("RGBA", (w, h))
    top, bot = _hex(c_top), _hex(c_bottom)
    px = grad.load()
    for y in range(h):
        row = _lerp(top, bot, y / max(1, h - 1)) + (255,)
        for x in range(w):
            px[x, y] = row
    grad.putalpha(mask)
    return grad, bbox


def draw_wordmark(im, cx, cy, size, gap=0.06):
    """把「竹梅」畫在 (cx, cy) 中心，字高 size。回實際總寬。"""
    fnt = font(size)
    chu, bb1 = gradient_char("竹", fnt, *GRAD_CHU)
    mei, bb2 = gradient_char("梅", fnt, *GRAD_MEI)
    g = round(size * gap)
    total_w = chu.width + g + mei.width
    top = cy - max(chu.height, mei.height) // 2
    x = cx - total_w // 2
    im.paste(chu, (x, top), chu)
    im.paste(mei, (x + chu.width + g, top), mei)
    return total_w


def draw_tracked(draw, im, cx, y, text, size, fill, tracking=0.28):
    """置中、含字距的一行字。"""
    fnt = font(size)
    widths = [draw.textlength(c, font=fnt) for c in text]
    t = round(size * tracking)
    total = sum(widths) + t * (len(text) - 1)
    x = cx - total / 2
    for c, w in zip(text, widths):
        draw.text((x, y), c, font=fnt, fill=fill)
        x += w + t


def logo_mark(s):
    im = Image.new("RGB", (s, s), BG)
    draw_wordmark(im, s // 2, s // 2, round(s * 0.46))
    return im


def logo_square(s):
    im = Image.new("RGB", (s, s), BG)
    d = ImageDraw.Draw(im)
    draw_wordmark(im, s // 2, round(s * 0.40), round(s * 0.40))
    draw_tracked(d, im, s // 2, round(s * 0.64), "活動觀測站", round(s * 0.115), WHITE)
    return im


def logo_bot(s):
    # 頭貼會被裁圓，字縮小置中留安全邊
    im = Image.new("RGB", (s, s), BG)
    draw_wordmark(im, s // 2, s // 2, round(s * 0.34))
    return im


def _bubble(im, box, radius, tail, fill_top, fill_bottom):
    """漸層對話泡泡＋小尾巴。tail=('bl'|'tr', (x1,y1,x2,y2,x3,y3))"""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, radius=radius, fill="#FFFFFF")
    d.polygon(tail, fill="#FFFFFF")
    mask = layer.split()[3]
    grad = Image.new("RGB", im.size, BG)
    top, bot = _hex(fill_top), _hex(fill_bottom)
    gd = ImageDraw.Draw(grad)
    for y in range(y0 - h // 4, y1 + h // 4 + 1):
        gd.line([(0, y), (im.width, y)],
                fill=_lerp(top, bot, min(1, max(0, (y - y0) / max(1, h)))))
    im.paste(grad, (0, 0), mask)


def logo_chat(s):
    im = Image.new("RGB", (s, s), BG)
    u = s / 512
    # 藍泡「竹」左上、紫泡「梅」右下（沿用 2026-08 版構圖）
    b1 = (round(56 * u), round(76 * u), round(268 * u), round(268 * u))
    _bubble(im, b1, round(48 * u),
            (round(92 * u), round(250 * u), round(74 * u), round(312 * u), round(150 * u), round(266 * u)),
            *GRAD_CHU)
    b2 = (round(230 * u), round(238 * u), round(442 * u), round(430 * u))
    _bubble(im, b2, round(48 * u),
            (round(406 * u), round(256 * u), round(442 * u), round(196 * u), round(352 * u), round(244 * u)),
            *GRAD_MEI)
    fnt = font(round(118 * u))
    d = ImageDraw.Draw(im)
    for ch, box in (("竹", b1), ("梅", b2)):
        bb = d.textbbox((0, 0), ch, font=fnt)
        d.text(((box[0] + box[2]) / 2 - (bb[0] + bb[2]) / 2,
                (box[1] + box[3]) / 2 - (bb[1] + bb[3]) / 2), ch, font=fnt, fill="#FFFFFF")
    return im


def og_default():
    im = Image.new("RGB", (1200, 630), BG)
    d = ImageDraw.Draw(im)
    draw_wordmark(im, 600, 250, 300, gap=0.18)
    draw_tracked(d, im, 600, 438, "活動觀測站", 60, WHITE)
    sub = "清大 × 交大校園活動自動彙整"
    f2 = font(34)
    d.text((600 - d.textlength(sub, font=f2) / 2, 532), sub, font=f2, fill=MUTED)
    return im


def main():
    if not FONT_PATH.exists():
        raise SystemExit(f"缺字型 {FONT_PATH}，下載方式見檔頭 docstring")
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    big = {"logo-mark": logo_mark(1024), "logo-square": logo_square(1024),
           "logo-bot": logo_bot(1024), "logo-chat": logo_chat(1024)}
    sizes = {"logo-mark": (16, 32, 48, 64, 256, 1024),
             "logo-square": (32, 64, 180, 192, 256, 512, 1024),
             "logo-bot": (192, 512, 1024), "logo-chat": (512, 1024)}
    for name, master in big.items():
        for s in sizes[name]:
            out = master if s == 1024 else master.resize((s, s), Image.LANCZOS)
            out.save(BRAND_DIR / f"{name}-{s}.png", "PNG")
            print(f"{name}-{s}.png")
    og_default().save(ROOT / "site" / "assets" / "og-default.png", "PNG")
    print("og-default.png")


if __name__ == "__main__":
    main()
