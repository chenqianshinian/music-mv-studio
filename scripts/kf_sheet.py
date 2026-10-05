# -*- coding: utf-8 -*-
"""把首帧闸门的 kf / kf1x 拼成带镜号的总览图，供人工看片。

用法：python kf_sheet.py <输出jpg> <kf|kf1> [每行=10] [每张宽=200]
环境变量：MV_BANK（分镜库 JSON，决定镜号顺序）、MV_KF_DIR（首帧目录）
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _mvcfg import FONT_UI, get, resolve_font  # noqa: E402

KF_DIR = get("MV_KF_DIR")
BANK = get("MV_BANK")


def main():
    out, kind = sys.argv[1], sys.argv[2]
    cols = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    tw = int(sys.argv[4]) if len(sys.argv) > 4 else 200
    th = int(round(tw * 1344 / 768))
    if not (KF_DIR and BANK):
        sys.exit("请设 MV_KF_DIR（首帧目录）与 MV_BANK（分镜库 JSON）")
    bank = __import__("json").load(io.open(BANK, encoding="utf-8"))
    order = [s["key"] for s in bank["shots"]]
    items = []
    for k in order:
        fn = ("kf_%s_0.png" % k) if kind == "kf" else ("kf1x_%s.png" % k)
        p = os.path.join(KF_DIR, fn)
        if os.path.exists(p) and os.path.getsize(p) > 5000:
            items.append((k, p))
    if not items:
        print("no images for kind=%s" % kind)
        return
    rows = (len(items) + cols - 1) // cols
    band = 30
    sheet = Image.new("RGB", (tw * cols, (th + band) * rows), (12, 14, 18))
    dr = ImageDraw.Draw(sheet)
    try:
        fnt = ImageFont.truetype(resolve_font(FONT_UI) or "", max(14, tw // 11))
    except (OSError, TypeError):
        fnt = ImageFont.load_default()
    for i, (k, p) in enumerate(items):
        x, y = (i % cols) * tw, (i // cols) * (th + band)
        sheet.paste(Image.open(p).convert("RGB").resize((tw, th), Image.LANCZOS), (x, y))
        dr.text((x + 6, y + th + 5), k, font=fnt, fill=(255, 214, 90))
    sheet.save(out, quality=88)
    print("sheet: %s  %s  %d 张  %dx%d" % (out, kind, len(items), sheet.size[0], sheet.size[1]))


if __name__ == "__main__":
    main()
