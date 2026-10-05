# -*- coding: utf-8 -*-
"""从成片里均匀抽帧并拼成带时间码的质检图。
用法：grab_frames.py <视频> <输出jpg> [张数=24] [每行=6]
"""
import os
import subprocess
import sys
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _mvcfg import FFMPEG, FFPROBE, FONT_UI, NO_WIN, resolve_font


src, out = sys.argv[1], sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 24
cols = int(sys.argv[4]) if len(sys.argv) > 4 else 6
_probe = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                         "-of", "csv=p=0", src], capture_output=True, text=True,
                        creationflags=NO_WIN)
try:
    dur = float(_probe.stdout.strip())
except ValueError:
    sys.exit("拿不到时长：ffprobe 失败（设 FFPROBE_BIN 或检查视频路径）\n  %s"
             % ((_probe.stderr or "").strip() or _probe.stdout.strip()))
tmp = out + "_frames"
os.makedirs(tmp, exist_ok=True)
TW, TH = 320, 568
rows = (n + cols - 1) // cols
sheet = Image.new("RGB", (TW * cols, TH * rows), (14, 16, 20))
dr = ImageDraw.Draw(sheet)
try:  # 时间码用跨平台能画中文/数字的字体（以前写死 arialbd.ttf，非 Windows 上必然回退）
    fnt = ImageFont.truetype(resolve_font(FONT_UI) or "", 26)
except (OSError, TypeError):
    fnt = ImageFont.load_default()
for i in range(n):
    t = dur * (i + 0.5) / n
    fp = os.path.join(tmp, "f%02d.jpg" % i)
    subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", "%.3f" % t, "-i", src,
                    "-frames:v", "1", "-q:v", "3", fp], check=False, creationflags=NO_WIN)
    if not os.path.exists(fp):
        continue
    im = Image.open(fp).convert("RGB").resize((TW, TH), Image.LANCZOS)
    x, y = (i % cols) * TW, (i // cols) * TH
    sheet.paste(im, (x, y))
    label = "%d:%05.2f" % (int(t // 60), t % 60)
    dr.rectangle([x + 4, y + 4, x + 4 + 15 * len(label), y + 36], fill=(0, 0, 0))
    dr.text((x + 10, y + 6), label, font=fnt, fill=(255, 220, 90))
sheet.save(out, quality=90)
print("sheet:", out, "duration %.2fs" % dur, n, "frames")
