# -*- coding: utf-8 -*-
"""A3-18「车是否持续往远处开」的像素判据（视觉模型会把方向读反，所以以像素序列为准）。

做法：按等间隔抽帧 → 在画面中下部找**绿色车体**的最大连通域 → 输出面积与中心纵坐标序列。
判据：面积序列必须**整体单调不增**（允许 ±15% 抖动、允许后段因为车太小而被阈值吃掉）。
用法：python check_a318_dir.py <clip.mp4> [--n 8] [--hi 3.3]
"""
import os
import subprocess
import sys

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FFMPEG = r"D:\om-setup\ffmpeg\ffmpeg-8.1.2-essentials_build\bin\ffmpeg.exe"
TMP = r"E:\MV-temp\huoluomuzi-v3\check\_frames_tmp"


def car_area(png):
    a = np.asarray(Image.open(png).convert("RGB")).astype(int)
    h, w, _ = a.shape
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    m = (G > R + 6) & (G > B + 6) & (G > 40)
    m[: int(h * 0.25), :] = False
    m[:, : int(w * 0.15)] = False
    m[:, int(w * 0.85):] = False
    seen = np.zeros((h, w), bool)
    best = None
    ys, xs = np.nonzero(m)
    for sy, sx in zip(ys, xs):
        if seen[sy, sx]:
            continue
        stack = [(sy, sx)]
        seen[sy, sx] = True
        n = 0
        cy = cx = 0
        while stack:
            y, x = stack.pop()
            n += 1
            cy += y
            cx += x
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and m[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        if n > 60 and 200 < cx / n < 560 and 200 < cy / n < 900:
            if best is None or n > best[0]:
                best = (n, cx / n / w, cy / n / h)
    return best


def main():
    clip = sys.argv[1]
    n = 8
    hi = 3.3
    if "--n" in sys.argv:
        n = int(sys.argv[sys.argv.index("--n") + 1])
    if "--hi" in sys.argv:
        hi = float(sys.argv[sys.argv.index("--hi") + 1])
    tag = os.path.splitext(os.path.basename(clip))[0]
    outd = os.path.join(TMP, tag)
    os.makedirs(outd, exist_ok=True)
    seq = []
    for i in range(n):
        t = hi * i / max(1, n - 1)
        png = os.path.join(outd, "t%02d.png" % i)
        subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", "%.3f" % t, "-i", clip,
                        "-frames:v", "1", png], check=False,
                       creationflags=0x08000000)
        r = car_area(png)
        seq.append((t, r))
    print("== %s（使用窗口 0–%.1fs）" % (tag, hi))
    print("   t    面积   中心x%%  中心y%%")
    for t, r in seq:
        if r:
            print("  %4.2f  %5d   %5.1f   %5.1f" % (t, r[0], r[1] * 100, r[2] * 100))
        else:
            print("  %4.2f    -      -       -   (没找到绿色车体)" % t)
    areas = [r[0] for _, r in seq if r]
    if len(areas) >= 3:
        grow = (areas[-1] - areas[0]) / max(1, areas[0])
        ok = areas[-1] <= areas[0] * 1.15
        print("  首帧 %d → 末帧 %d（变化 %+.0f%%，允许 +15%% 抖动）→ %s"
              % (areas[0], areas[-1], grow * 100, "单向（合格）" if ok else "变大＝不合格"))


if __name__ == "__main__":
    main()
