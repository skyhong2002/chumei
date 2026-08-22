"""LINE 圖文選單（rich menu）一次性設置：產圖 → 註冊 → 上傳 → 設為全體預設。

聊天室底部的常駐按鈕面板，點按即代打字送出查詢（走 message action，
所以回覆仍是免費的 Reply API）。重跑會先刪掉舊的 chumei- 選單再建新的。
圖也存一份在 state/line_richmenu.png 方便檢視。

用法：.venv/bin/python scripts/setup_line_richmenu.py
"""

import requests
from PIL import Image, ImageDraw, ImageFont

import bot_line
from chumei_lib import ROOT

API = "https://api.line.me/v2/bot"
API_DATA = "https://api-data.line.me/v2/bot"
IMG_PATH = ROOT / "state" / "line_richmenu.png"

W, H = 2500, 1686
# 品牌統一字型（同 make_brand.py；缺檔時下載方式見該檔 docstring）
FONT = str(ROOT / "state" / "fonts" / "NotoSansTC-Bold.otf")

# 暗色設計系統（同 make_brand.py / 網站深色 tokens）：梅＝清大紫、竹＝交大藍
INK = "#F5F7FF"
CANVAS = "#000000"
CARD = "#111111"
BORDER = "#2B2B2B"
BLUE = "#5A78FF"
PLUM = "#C069DD"
GRAY = "#9EA8BF"

# (標籤, 送出的文字, accent 色)，3×2
CELLS = [
    ("今天", "今天", BLUE), ("這週末", "這週末", BLUE), ("下週", "下週", BLUE),
    ("清大", "清大", PLUM), ("交大", "交大", BLUE), ("使用說明", "說明", GRAY),
]


def render_image():
    im = Image.new("RGB", (W, H), CANVAS)
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype(FONT, 168)
    margin, gap = 48, 36
    cw = (W - margin * 2 - gap * 2) // 3
    ch = (H - margin * 2 - gap) // 2
    areas = []
    for i, (label, text, accent) in enumerate(CELLS):
        col, row = i % 3, i // 3
        x = margin + col * (cw + gap)
        y = margin + row * (ch + gap)
        d.rounded_rectangle([x, y, x + cw, y + ch], radius=48,
                            fill=CARD, outline=BORDER, width=4)
        bbox = d.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = x + (cw - tw) // 2 - bbox[0]
        ty = y + (ch - th) // 2 - bbox[1] - 40
        d.text((tx, ty), label, font=font, fill=INK)
        bar_w = 140
        bar_y = ty + bbox[1] + th + 88
        d.rounded_rectangle([x + (cw - bar_w) // 2, bar_y,
                             x + (cw + bar_w) // 2, bar_y + 18],
                            radius=9, fill=accent)
        areas.append({
            "bounds": {"x": x, "y": y, "width": cw, "height": ch},
            "action": {"type": "message", "label": label, "text": text},
        })
    IMG_PATH.parent.mkdir(parents=True, exist_ok=True)
    im.save(IMG_PATH, "PNG")
    return areas


def main():
    headers = {"Authorization": f"Bearer {bot_line.access_token()}"}

    old = requests.get(f"{API}/richmenu/list", headers=headers, timeout=15).json()
    for menu in old.get("richmenus", []):
        if menu.get("name", "").startswith("chumei-"):
            requests.delete(f"{API}/richmenu/{menu['richMenuId']}", headers=headers, timeout=15)
            print(f"deleted old {menu['richMenuId']}")

    areas = render_image()
    r = requests.post(f"{API}/richmenu", headers=headers, timeout=15, json={
        "size": {"width": W, "height": H},
        "selected": True,
        "name": "chumei-main",
        "chatBarText": "快速查詢",
        "areas": areas,
    })
    r.raise_for_status()
    menu_id = r.json()["richMenuId"]
    print(f"created {menu_id}")

    r = requests.post(f"{API_DATA}/richmenu/{menu_id}/content",
                      headers={**headers, "Content-Type": "image/png"},
                      data=IMG_PATH.read_bytes(), timeout=30)
    r.raise_for_status()
    print("image uploaded")

    r = requests.post(f"{API}/user/all/richmenu/{menu_id}", headers=headers, timeout=15)
    r.raise_for_status()
    print("set as default for all users")


if __name__ == "__main__":
    main()
