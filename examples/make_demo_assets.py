# -*- coding: utf-8 -*-
"""生成"零 API 消耗"的示例素材：4 段合成镜头 + 一条 SRT + 一条占位音轨。

目的是让任何人 clone 之后**不花一分钱、不配密钥**就能把合成器跑通，
先看到"片段 → 整片"这一段的效果，再去接真接口。

用法：
    python examples/make_demo_assets.py [输出目录=./demo]

产出：
    <out>/clips/shot_A1-1.mp4 ... shot_A1-4.mp4     （与 examples/song-a-bank.json 的 key 对应）
    <out>/song-a.srt                                （4 条 cue，与分镜库时间轴对齐）
    <out>/song-a-tone.m4a                           （占位音轨，14.2 秒）

接着（Windows cmd 示例）：
    set ZDN_BANK=examples\\song-a-bank.json
    set ZDN_CLIPS=<out>\\clips
    set ZDN_SRT=<out>\\song-a.srt
    set ZDN_AUDIO=<out>\\song-a-tone.m4a
    set ZDN_OUT=<out>\\song-a-mv.mp4
    set ZDN_TOTAL=14.2
    set ZDN_FADE_OUT=12,2
    python scripts\\compose_mv.py
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from _mvcfg import FFMPEG  # noqa: E402

# key 必须与 examples/song-a-bank.json 里的 key 一致
SHOTS = [
    ("A1-1", "0x2B3A55", "0xD8E4F0", 5.0),   # 冷蓝夜色：薄雾
    ("A1-2", "0x35506B", "0xF0E0C0", 5.0),   # 河湾：纸船
    ("A1-3", "0x4A3B2E", "0xFFD9A0", 5.0),   # 暖木色：茶碗
    ("A1-4", "0x6B7F8C", "0xFFFFFF", 5.0),   # 灰蓝远景：两个剪影
]

SRT = """1
00:00:00,000 --> 00:00:03,600
（示例）第一句

2
00:00:03,600 --> 00:00:07,400
（示例）第二句

3
00:00:07,400 --> 00:00:11,000
（示例）第三句

4
00:00:11,000 --> 00:00:14,200
（示例）第四句
"""


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.getcwd(), "demo")
    clips = os.path.join(out, "clips")
    os.makedirs(clips, exist_ok=True)

    for key, bg, fg, dur in SHOTS:
        dst = os.path.join(clips, "shot_%s.mp4" % key)
        # 一块色块横穿画面 = 保证成片"真的在动"，方便肉眼确认合成与溶解是否正确；
        # 再叠一点时间噪声，让它有真实码率（纯色片会被压到几 KB，和真素材差太远）
        vf = ("drawbox=x='mod(t*190,768+120)-120':y=860:w=120:h=120:"
              "color=%s:t=fill,noise=alls=12:allf=t" % fg)
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i",
                        "color=c=%s:s=768x1344:d=%.2f:r=24" % (bg, dur),
                        "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "22", "-pix_fmt", "yuv420p", dst], check=True)
        print("made", dst)

    srt = os.path.join(out, "song-a.srt")
    with open(srt, "w", encoding="utf-8", newline="\n") as f:
        f.write(SRT)
    print("made", srt)

    tone = os.path.join(out, "song-a-tone.m4a")
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "sine=frequency=330:duration=14.2",
                    "-c:a", "aac", "-b:a", "128k", tone], check=True)
    print("made", tone)

    print("\n下一步环境变量：")
    print("  ZDN_BANK=examples%ssong-a-bank.json" % os.sep)
    print("  ZDN_CLIPS=%s" % clips)
    print("  ZDN_SRT=%s" % srt)
    print("  ZDN_AUDIO=%s" % tone)
    print("  ZDN_OUT=%s" % os.path.join(out, "song-a-mv.mp4"))
    print("  ZDN_TOTAL=14.2")
    print("  ZDN_FADE_OUT=12,2")
    print("  python scripts%1$scompose_mv.py".replace("%1$s", os.sep))


if __name__ == "__main__":
    main()
