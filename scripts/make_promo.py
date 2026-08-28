"""宣傳圖產生器 — 沿用 make_brand 的品牌系統（黑底＋Noto Sans TC Bold＋竹藍/梅紫漸層）。

輸入：state/promo/shot-{home,calendar,stories}.png（playwright 390×844@3x 手機截圖）
輸出：state/promo/out/
  hero-4x5.png       1080×1350  Threads/IG 主圖（首頁截圖手機框＋數字）
  story-9x16.png     1080×1920  IG/FB 限時動態
  hero-1x1.png       1080×1080  Dcard/FB 縮圖
  slide-{1..4}.png   1080×1350  輪播：功能介紹四張
  cover-16x9.png     1200×630   Dcard/連結預覽

用法：.venv/bin/python scripts/make_promo.py
"""
import json
from datetime import datetime
from PIL import Image, ImageDraw, ImageFilter

from chumei_lib import ROOT
from make_brand import BG, WHITE, MUTED, GRAD_CHU, GRAD_MEI, font, draw_wordmark, _hex, _lerp

SHOTS = ROOT / "state" / "promo"
OUT = SHOTS / "out"


def stats():
    ev = json.load(open(ROOT / "site/api/events.json"))
    ev = ev["events"] if isinstance(ev, dict) else ev
    now = datetime.now().isoformat()
    src = json.load(open(ROOT / "site/data/sources.json"))["entries"]
    return {
        "events": len(ev),
        "upcoming": sum(1 for e in ev if (e.get("start_at") or "") >= now),
        "orgs": sum(1 for s in src if s["events"] > 0),
    }


def gradient_text(draw_target, xy, text, size, c_top, c_bottom):
    """整段文字縱向漸層（左上角定位）。"""
    fnt = font(size)
    d = ImageDraw.Draw(draw_target)
    bb = d.textbbox((0, 0), text, font=fnt)
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((-bb[0], -bb[1]), text, font=fnt, fill=255)
    grad = Image.new("RGBA", (w, h))
    px = grad.load()
    top, bot = _hex(c_top), _hex(c_bottom)
    for y in range(h):
        row = _lerp(top, bot, y / max(1, h - 1)) + (255,)
        for x in range(w):
            px[x, y] = row
    grad.putalpha(mask)
    draw_target.paste(grad, (xy[0] + bb[0], xy[1] + bb[1]), grad)
    return w


def glow(im, cx, cy, r, color, alpha=90):
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse((cx - r, cy - r, cx + r, cy + r), fill=_hex(color) + (alpha,))
    layer = layer.filter(ImageFilter.GaussianBlur(r * 0.55))
    im.paste(Image.alpha_composite(im.convert("RGBA"), layer).convert("RGB"))


def phone(shot_name, width, crop_h=None, crop_top=0):
    """把截圖裝進圓角手機框。回 RGBA。"""
    shot = Image.open(SHOTS / f"shot-{shot_name}.png").convert("RGB")
    scale = width / shot.width
    shot = shot.resize((width, round(shot.height * scale)), Image.LANCZOS)
    if crop_h:
        shot = shot.crop((0, crop_top, width, min(shot.height, crop_top + crop_h)))
    pad = round(width * 0.035)
    r = round(width * 0.11)
    W, H = shot.width + pad * 2, shot.height + pad * 2
    frame = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(frame)
    d.rounded_rectangle((0, 0, W - 1, H - 1), radius=r, fill="#141622", outline="#2A2E42", width=3)
    mask = Image.new("L", shot.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, shot.width - 1, shot.height - 1), radius=r - pad, fill=255)
    frame.paste(shot, (pad, pad), mask)
    return frame


def paste_phone_fade(im, ph, x, y, fade=220):
    """貼手機框，底部漸隱到黑（截圖被裁的地方不會有硬邊）。"""
    ph = ph.copy()
    a = ph.split()[3]
    fd = ImageDraw.Draw(a)
    h = ph.height
    for i in range(fade):
        yy = h - fade + i
        fd.line([(0, yy), (ph.width, yy)], fill=round(255 * (1 - i / fade)))
    ph.putalpha(a)
    im.paste(ph, (x, y), ph)


def text_center(im, y, text, size, fill):
    d = ImageDraw.Draw(im)
    f = font(size)
    d.text((im.width / 2 - d.textlength(text, font=f) / 2, y), text, font=f, fill=fill)


def wordmark_line(im, cx, cy, size):
    """「竹梅活動觀測站」一行：竹梅漸層＋白字副標。"""
    d = ImageDraw.Draw(im)
    f = font(size)
    rest = "活動觀測站"
    rest_w = d.textlength(rest, font=f)
    wm_w = round(size * 2.06)
    gap = round(size * 0.12)
    total = wm_w + gap + rest_w
    x0 = cx - total / 2
    draw_wordmark(im, round(x0 + wm_w / 2), cy, size)
    bb = d.textbbox((0, 0), rest, font=f)
    d.text((x0 + wm_w + gap, cy - (bb[1] + bb[3]) / 2), rest, font=f, fill=WHITE)


def stat_row(im, y, items, size=64, label_size=28):
    d = ImageDraw.Draw(im)
    n = len(items)
    col = im.width / n
    for i, (num, label, grad) in enumerate(items):
        cx = col * i + col / 2
        f = font(size)
        w = d.textlength(num, font=f)
        gradient_text(im, (round(cx - w / 2), y), num, size, *grad)
        fl = font(label_size)
        d.text((cx - d.textlength(label, font=fl) / 2, y + size + 14), label, font=fl, fill=MUTED)


def hero(W, H, s, top_offset=0):
    im = Image.new("RGB", (W, H), BG)
    glow(im, round(W * 0.2), round(H * 0.15), 420, GRAD_CHU[0], 70)
    glow(im, round(W * 0.85), round(H * 0.35), 420, GRAD_MEI[0], 60)
    tall = H > W
    wordmark_line(im, W // 2, (130 if tall else 100) + top_offset, 84 if tall else 72)
    y = (230 if tall else 180) + top_offset
    text_center(im, y, "陽明/交大、清大", 70 if tall else 58, WHITE)
    text_center(im, y + (94 if tall else 78), "校園活動資訊一站看完", 70 if tall else 58, WHITE)
    text_center(im, y + (215 if tall else 180),
                "社團・演講・表演・市集，一站彙整，每 3 小時更新", 30 if tall else 27, MUTED)
    items = [(f"{s['events']:,}", "場活動已收錄", GRAD_CHU),
             (f"{s['upcoming']}", "場即將登場", GRAD_MEI),
             (f"{s['orgs']}", "個社團・單位", GRAD_CHU)]
    stat_row(im, y + (290 if tall else 240), items, 68 if tall else 56, 28 if tall else 24)
    pw = 560 if tall else 470
    py = y + (460 if tall else 370)
    bottom = H - 150
    ph = phone("home", pw, crop_h=bottom - py - round(pw * 0.07))
    paste_phone_fade(im, ph, (W - ph.width) // 2, py, fade=200)
    text_center(im, H - 92, "https://竹梅.tw", 32, MUTED)
    return im


def slide(title, sub, shot_name, W=1080, H=1350, grad=GRAD_CHU, crop_top=0, index=None):
    im = Image.new("RGB", (W, H), BG)
    glow(im, W // 2, round(H * 0.1), 460, grad[0], 60)
    d = ImageDraw.Draw(im)
    if index:
        d.text((72, 64), index, font=font(30), fill=MUTED)
    d.text((72, 120), title, font=font(72), fill=WHITE)
    f = font(32)
    yy = 230
    for line in sub.split("\n"):
        d.text((72, yy), line, font=f, fill=MUTED)
        yy += 48
    ph = phone(shot_name, 620, crop_h=H - 150 - 380 - 44, crop_top=crop_top)
    paste_phone_fade(im, ph, (W - ph.width) // 2, 380, fade=200)
    wordmark_line(im, W // 2, H - 80, 36)
    return im


def cover(s):
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), BG)
    glow(im, 200, 100, 380, GRAD_CHU[0], 70)
    glow(im, 1000, 550, 380, GRAD_MEI[0], 60)
    d = ImageDraw.Draw(im)
    draw_wordmark(im, 360, 200, 180)
    cover_label = "活動觀測站"
    cover_label_font = font(72)
    d.text((360 - d.textlength(cover_label, font=cover_label_font) / 2, 280),
           cover_label, font=cover_label_font, fill=WHITE)
    d.text((90, 405), "陽明/交大、清大校園活動資訊一站看完", font=font(30), fill=MUTED)
    ph = phone("home", 400, crop_h=560)
    paste_phone_fade(im, ph, 720, 50, fade=180)
    domain = "https://竹梅.tw"
    domain_font = font(24)
    d.text((360 - d.textlength(domain, font=domain_font) / 2, 505),
           domain, font=domain_font, fill=MUTED)
    return im


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    s = stats()
    print(s)
    hero(1080, 1350, s).save(OUT / "hero-4x5.png")
    hero(1080, 1080, s).save(OUT / "hero-1x1.png")
    hero(1080, 1920, s, top_offset=110).save(OUT / "story-9x16.png")
    cover(s).save(OUT / "cover-16x9.png")
    slides = [
        ("活動資訊，一條河道", "IG、FB、校內公告自動彙整\n不用逐一追蹤", "home", GRAD_CHU, 0),
        ("直接看日曆", "日期、時間、地點一眼看懂\n一鍵加入或訂閱行事曆", "calendar", GRAD_MEI, 0),
        ("限動也幫你收好", "陽明/交大、清大社團限動集中看\n24 小時內消息不漏接", "stories", GRAD_CHU, 0),
        ("地圖找附近活動", "依校區、日期、類型快速篩選\n直接看活動在哪裡", "events", GRAD_MEI, 280),
    ]
    for i, (t, sub, shot, g, crop) in enumerate(slides, 1):
        slide(t, sub, shot, grad=g, crop_top=crop, index=f"{i} / {len(slides)}").save(OUT / f"slide-{i}.png")
    print("ok →", OUT)


if __name__ == "__main__":
    main()
