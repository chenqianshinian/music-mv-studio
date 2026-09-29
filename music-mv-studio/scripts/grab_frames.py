# -*- coding: utf-8 -*-
"""从成片里均匀抽帧并拼成带时间码的质检图。
用法：grab_frames.py <视频> <输出jpg> [张数=24] [每行=6]
"""
import os
import subprocess
import sys
from PIL import Image, ImageDraw, ImageFont

FFMPEG = r"D:\om-setup\ffmpeg\ffmpeg-8.1.2-essentials_build\bin\ffmpeg.exe"
FFPROBE = r"D:\om-setup\ffmpeg\ffmpeg-8.1.2-essentials_build\bin\ffprobe.exe"
NO_WIN = 0x08000000   # 子进程静默，避免闪控制台窗口

src, out = sys.argv[1], sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 24
cols = int(sys.argv[4]) if len(sys.argv) > 4 else 6
dur = float(subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", src], capture_output=True, text=True,
                           creationflags=NO_WIN).stdout.strip())
tmp = out + "_frames"
os.makedirs(tmp, exist_ok=True)
TW, TH = 320, 568
rows = (n + cols - 1) // cols
sheet = Image.new("RGB", (TW * cols, TH * rows), (14, 16, 20))
dr = ImageDraw.Draw(sheet)
fnt = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 26)
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
