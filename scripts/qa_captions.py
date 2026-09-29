# -*- coding: utf-8 -*-
"""字幕存在性与时轴自动校验（不靠肉眼）。

原理：取字幕带 y=1490..1670，统计"亮字像素"（min(R,G,B) > 180）占比。
判据：每个 cue 中点应出现明显峰值；前奏/间奏/尾奏等无 cue 段应接近 0。

用法：qa_captions.py <成片> <srt> [字幕带中心y=1580] [亮字阈值=180]

阈值口径（踩过的坑）：暖木色/暖墨色字幕的最暗通道只有 ~158，用 180 会**假报"没有字幕"**。
出现 0.00% 先把阈值降到 140 复测，再下"确实漏字"的结论。
"""
import io
import os
import subprocess
import sys

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # 提示里带中文歌词，避免控制台编码把字弄乱
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _mvcfg import FFMPEG, MV_TMP  # noqa: E402


def parse_srt(path):
    cues = []
    for block in io.open(path, encoding="utf-8-sig").read().replace("\r", "").split("\n\n"):
        lines = block.strip().split("\n")
        if len(lines) < 2 or "-->" not in lines[1]:
            continue
        a, b = lines[1].split("-->")

        def t(s):
            h, m, sec = s.strip().split(":")[:3]
            return int(h) * 3600 + int(m) * 60 + float(sec.replace(",", "."))
        cues.append((t(a), t(b), " ".join(lines[2:]).strip()))
    return cues


THR = 180  # 2026-09-24：暖木色/暖墨色字幕最暗通道 ~158，180 会假报「没有字幕」，可用第 4 个参数下调


def band_ratio(video, t, cy, half=90, tmp=None):
    tmp = tmp or os.path.join(MV_TMP, "_qa_caption.jpg")
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", "%.3f" % t, "-i", video,
                    "-frames:v", "1", "-q:v", "2", tmp], check=False,
                   creationflags=0x08000000)
    if not os.path.exists(tmp):
        return -1.0
    im = np.asarray(Image.open(tmp).convert("RGB"))
    band = im[max(0, cy - half):cy + half]
    bright = (band.min(axis=2) > THR)
    return float(bright.mean() * 100)


def main():
    global THR
    video, srt = sys.argv[1], sys.argv[2]
    cy = int(sys.argv[3]) if len(sys.argv) > 3 else 1580
    if len(sys.argv) > 4:
        THR = int(sys.argv[4])
    cues = parse_srt(srt)
    print("%d cues" % len(cues))
    vals = []
    for i, (s, e, txt) in enumerate(cues, 1):
        r = band_ratio(video, (s + e) / 2, cy)
        vals.append(r)
        print("cue %-2d %7.2f-%7.2f  bright=%5.2f%%  %s" % (i, s, e, r, txt[:22]))
    # 无字幕段：取每两个 cue 之间的中点（间隔 >0.6s 的）
    gaps = []
    for i in range(len(cues) - 1):
        a, b = cues[i][1], cues[i + 1][0]
        if b - a > 0.6:
            gaps.append((sort_mid(a, b), a, b))
    if cues and cues[0][0] > 1.0:
        gaps.append((cues[0][0] / 2, 0.0, cues[0][0]))
    print("--- 无字幕段（应接近 0）---")
    gvals = []
    for t, a, b in gaps:
        r = band_ratio(video, t, cy)
        gvals.append(r)
        print("gap %7.2f (%7.2f-%7.2f)  bright=%5.2f%%" % (t, a, b, r))
    print("SUMMARY cues n=%d mean=%.2f min=%.2f | gaps n=%d mean=%.3f max=%.3f"
          % (len(vals), float(np.mean(vals)), float(np.min(vals)),
             len(gvals), float(np.mean(gvals)) if gvals else -1,
             float(np.max(gvals)) if gvals else -1))


def sort_mid(a, b):
    return (a + b) / 2


if __name__ == "__main__":
    main()
