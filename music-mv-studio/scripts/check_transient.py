# -*- coding: utf-8 -*-
"""瞬现物检测：找出「只在某一帧出现、前后帧都没有」的东西（一闪即过的穿帮物）。

原理：对连续三帧 (i-1, i, i+1) 逐像素判断——
  当前帧与前后帧都不同（din、dout 都大），而**前后帧彼此几乎相同**（across 小）
→ 帧 i 上多出来的那块像素就是瞬现物。整幅变化（运镜/切换）会被 across 大排除掉。

用法：
  python check_transient.py <clip.mp4> [--lo 0.65] [--hi 3.85] [--fps 30] [--scale 480]
输出：每个候选的最强瞬现帧（时间、像素数），并把可疑帧裁剪放大存到 outdir（可选 --crop <目录>）。
"""
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FFMPEG = r"D:\om-setup\ffmpeg\ffmpeg-8.1.2-essentials_build\bin\ffmpeg.exe"
NO_WIN = 0x08000000


def analyze(clip, lo, hi, fps, sc, crop_dir=None, topn=3):
    d = tempfile.mkdtemp(prefix="tr_")
    subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", "%.3f" % lo, "-t", "%.3f" % (hi - lo),
                    "-i", clip, "-vf", "fps=%d,scale=%d:-2" % (fps, sc),
                    os.path.join(d, "%04d.jpg")], creationflags=NO_WIN)
    fs = sorted(os.listdir(d))
    arr = [np.asarray(Image.open(os.path.join(d, f)).convert("RGB"), dtype=np.float32) for f in fs]
    H, W = arr[0].shape[:2]
    rows = []
    for i in range(1, len(arr) - 1):
        a, b, c = arr[i - 1], arr[i], arr[i + 1]
        din = np.abs(b - a).mean(axis=2)
        dout = np.abs(b - c).mean(axis=2)
        across = np.abs(c - a).mean(axis=2)
        m = (din > 25) & (dout > 25) & (across < 12)
        rows.append((int(m.sum()), lo + i / float(fps), m, np.maximum(din, dout)))
    rows.sort(key=lambda r: -r[0])
    print("clip=%s  frames=%d  窗口 %.2f-%.2f" % (os.path.basename(clip), len(arr), lo, hi))
    for px, t, m, w in rows[:topn]:
        print("   瞬现 t=%.3fs  像素=%d  (全片最大瞬现=%d)" % (t, px, rows[0][0]))
    if crop_dir and rows and rows[0][0] >= 40:
        os.makedirs(crop_dir, exist_ok=True)
        for idx, (px, t, m, w) in enumerate(rows[:topn]):
            if px < 40:
                break
            ys, xs = np.where(w > np.percentile(w, 99.3))
            x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
            padx, pady = int(0.10 * W), int(0.10 * H)
            box = (max(0, x0 - padx), max(0, y0 - pady), min(W, x1 + padx), min(H, y1 + pady))
            for tag, tt in (("prev", t - 2.0 / fps), ("at", t), ("next", t + 2.0 / fps)):
                f = os.path.join(crop_dir, "t%.2f_%s.jpg" % (t, tag))
                subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", "%.3f" % max(0.0, tt),
                                "-i", clip, "-frames:v", "1", "-q:v", "2", f], creationflags=NO_WIN)
                im = Image.open(f)
                k = im.size[0] / float(W)
                im.crop((int(box[0] * k), int(box[1] * k), int(box[2] * k), int(box[3] * k))) \
                  .resize(((box[2] - box[0]) * 2, (box[3] - box[1]) * 2), Image.LANCZOS) \
                  .save(f, quality=95)
        print("   裁剪图 -> %s" % crop_dir)
    shutil.rmtree(d, ignore_errors=True)
    return rows[0][0] if rows else 0


def main():
    clip = sys.argv[1]
    def arg(name, default):
        return float(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default
    lo, hi, fps = arg("--lo", 0.65), arg("--hi", 3.85), int(arg("--fps", 30))
    sc = int(arg("--scale", 480))
    crop = sys.argv[sys.argv.index("--crop") + 1] if "--crop" in sys.argv else None
    analyze(clip, lo, hi, fps, sc, crop)


if __name__ == "__main__":
    main()
