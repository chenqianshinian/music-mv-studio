# -*- coding: utf-8 -*-
"""确定性 2.5D 运镜：把一张静图渲染成有缓慢机位的短视频（无生成模型、逐帧可复现）。

用途（**2026-09-25 已修正口径，见 SKILL §10**）：**只用于第二关键帧兜底与单镜返修**。
曾经用它替无人空镜省成本，被用户看片推翻——原话「很多河流、海鸥、鸟雀、烟雾、雪的镜头都不动……疑似幻灯片了」：
确定性运镜只给画面加**相机位移**，没有元素自身的物理运动（水不流、鸟不飞、烟不散、雪不落）。
现行口径：**空镜也走 i2v**，并逐镜写【运动锁】（§5 #19/#27）。

用法：
  python still_move.py <静图> <输出mp4> [秒数=5] [运动=push|pull|pan_left|pan_right|tilt_up|drift] [fps=24]

运动全部是确定的缓动（ease-in-out），无随机数；同参数重复渲染逐帧一致。
"""
import io
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image

from _mvcfg import FFMPEG, NO_WIN


# 每种运动：(缩放起点, 缩放终点, x 漂移比例, y 漂移比例)  —— 比例相对画面尺寸，正负决定方向
MOVES = {
    "push":      (1.00, 1.09, 0.0, 0.0),      # 缓慢推进
    "pull":      (1.09, 1.00, 0.0, 0.0),      # 缓慢拉远
    "pan_left":  (1.12, 1.12, 0.05, 0.0),     # 机位向左移（画面内容向右）
    "pan_right": (1.12, 1.12, -0.05, 0.0),
    "tilt_up":   (1.12, 1.12, 0.0, 0.045),    # 缓慢上摇
    "drift":     (1.06, 1.11, 0.02, -0.015),  # 边推边轻微漂移（默认质感位）
    # 幅度档位（2026-09-25 实测：i2v 空镜帧间差 ~11，drift 只有 3.5；
    # 需要"动感更足"时用这两档，不必回头找 i2v）
    "push_mid":  (1.00, 1.14, 0.0, 0.0),
    "push_fast": (1.00, 1.20, 0.0, 0.0),
}


def build(src, out, sec, move, fps):
    z0, z1, dx, dy = MOVES[move]
    W, H = Image.open(src).size
    # 先放大到 3 倍再 zoompan，避免缩放插值带来的抖动（zoompan 的 x/y 是整数像素）
    up = 3
    n = int(round(sec * fps))
    # ease-in-out：用 sin 曲线，起止速度都为 0，观感比线性"高级"且无突变
    t = "min(on/%d,1)" % (n - 1)
    ease = "(0.5-0.5*cos(PI*%s))" % t
    z = "%f+(%f-%f)*%s" % (z0, z1, z0, ease)
    # zoompan 的 x/y 是"取景框左上角"，居中后按比例偏移
    x = "iw/2-(iw/zoom/2)+(%f)*iw*%s" % (dx, ease)
    y = "ih/2-(ih/zoom/2)+(%f)*ih*%s" % (dy, ease)
    vf = ("scale=%d:%d:flags=lanczos," % (W * up, H * up)
          + "zoompan=z='%s':x='%s':y='%s':d=1:s=%dx%d:fps=%d," % (z, x, y, W, H, fps)
          + "format=yuv420p")
    cmd = [FFMPEG, "-y", "-v", "error", "-loop", "1", "-i", src, "-t", "%.3f" % sec,
           "-vf", vf, "-r", str(fps), "-c:v", "libx264", "-crf", "16",
           "-preset", "slow", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True, creationflags=NO_WIN)
    return out


def main():
    src, out = sys.argv[1], sys.argv[2]
    sec = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0
    move = sys.argv[4] if len(sys.argv) > 4 else "drift"
    fps = int(sys.argv[5]) if len(sys.argv) > 5 else 24
    if move not in MOVES:
        print("未知运动 %s，可选：%s" % (move, "/".join(MOVES)))
        sys.exit(2)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    build(src, out, sec, move, fps)
    print("ok %s  %.1fs  %s  %dfps  %.1fMB"
          % (out, sec, move, fps, os.path.getsize(out) / 1048576.0))


main()
