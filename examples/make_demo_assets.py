# -*- coding: utf-8 -*-
"""生成"零 API 消耗"的示例素材：4 段合成镜头 + 一条 SRT + 一条占位音轨。

目的是让任何人 clone 之后**不花一分钱、不配密钥**就能把合成器跑通，
先看到"片段 → 整片"这一段的效果，再去接真接口。

用法：
    python examples/make_demo_assets.py [输出目录=./demo] [--sec 5.0] [--fast]

    --sec   每段时长（秒），默认 5.0
    --fast  小体积/低码率模式（每段 4 秒、CRF 28、弱噪声），给 CI 冒烟测试用

产出：
    <out>/clips/shot_A1-1.mp4 ... shot_A1-4.mp4     （与 examples/song-a-bank.json 的 key 对应）
    <out>/song-a.srt                                （4 条 cue，与分镜库时间轴对齐）
    <out>/song-a-tone.m4a                           （占位音轨）

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
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from _mvcfg import FFMPEG  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK = os.path.join(ROOT, "examples", "song-a-bank.json")

# key 必须与 examples/song-a-bank.json 里的 key 一致
SHOTS = [
    ("A1-1", "0x2B3A55", "0xD8E4F0"),   # 冷蓝夜色：薄雾
    ("A1-2", "0x35506B", "0xF0E0C0"),   # 河湾：纸船
    ("A1-3", "0x4A3B2E", "0xFFD9A0"),   # 暖木色：茶碗
    ("A1-4", "0x6B7F8C", "0xFFFFFF"),   # 灰蓝远景：两个剪影
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


def bank_total():
    """成片总时长取分镜库里最后一镜的 t1（示例里是 14.2s）。"""
    try:
        with open(BANK, encoding="utf-8") as f:
            shots = json.load(f)["shots"]
        return float(max(s.get("t1") or 0 for s in shots))
    except Exception:
        return 14.2


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fast = "--fast" in sys.argv
    sec = 4.0 if fast else 5.0
    if "--sec" in sys.argv:
        sec = float(sys.argv[sys.argv.index("--sec") + 1])
    # 噪声是刻意加的：纯色片会被压到几 KB，和真素材差太远。但太强会让"示例"体积失控——
    # v3.0 的默认参数跑出 4×19MB 片段 + 88MB 成片，作为"5 分钟跑通"的示例偏重，故下调。
    crf = "28" if fast else "24"
    noise = "4" if fast else "8"

    out = args[0] if args else os.path.join(os.getcwd(), "demo")
    clips = os.path.join(out, "clips")
    os.makedirs(clips, exist_ok=True)

    for key, bg, fg in SHOTS:
        dst = os.path.join(clips, "shot_%s.mp4" % key)
        # 一块色块横穿画面 = 保证成片"真的在动"，方便肉眼确认合成与溶解是否正确
        vf = ("drawbox=x='mod(t*190,768+120)-120':y=860:w=120:h=120:"
              "color=%s:t=fill,noise=alls=%s:allf=t" % (fg, noise))
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i",
                        "color=c=%s:s=768x1344:d=%.2f:r=24" % (bg, sec),
                        "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", crf, "-pix_fmt", "yuv420p", dst], check=True)
        print("made %-34s %5.1f MB" % (dst, os.path.getsize(dst) / 1048576.0))

    srt = os.path.join(out, "song-a.srt")
    with open(srt, "w", encoding="utf-8", newline="\n") as f:
        f.write(SRT)
    print("made", srt)

    total = bank_total()
    tone = os.path.join(out, "song-a-tone.m4a")
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "sine=frequency=330:duration=%.2f" % total,
                    "-c:a", "aac", "-b:a", "128k", tone], check=True)
    print("made", tone)

    print("\n下一步环境变量：")
    print("  ZDN_BANK=examples%ssong-a-bank.json" % os.sep)
    print("  ZDN_CLIPS=%s" % clips)
    print("  ZDN_SRT=%s" % srt)
    print("  ZDN_AUDIO=%s" % tone)
    print("  ZDN_OUT=%s" % os.path.join(out, "song-a-mv.mp4"))
    print("  ZDN_TOTAL=%.1f" % total)
    print("  ZDN_FADE_OUT=%.0f,2" % (total - 2.2))
    print("  python scripts%1$scompose_mv.py".replace("%1$s", os.sep))


if __name__ == "__main__":
    main()
