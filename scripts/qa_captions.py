# -*- coding: utf-8 -*-
"""字幕存在性与时轴自动校验（不靠肉眼）。

原理：取字幕带 y=1490..1670，统计"亮字像素"（min(R,G,B) > THR）占比。
判据：每个 cue 中点应出现明显峰值；前奏/间奏/尾奏等无 cue 段应接近 0。

用法：qa_captions.py <成片> <srt> [字幕带中心y=1580] [亮字阈值=180] [--min-bright 0.05]

退出码：0 = 每条 cue 都有峰值；1 = 有 cue 低于 --min-bright；2 = 抽帧失败（视频/路径问题）；
        3 = 没有一条 cue 落在成片时长内（成片太短或 SRT 与成片不匹配，判据不成立，不算通过）

阈值口径（踩过的坑）：暖木色/暖墨色字幕的最暗通道只有 ~158，用 180 会**假报"没有字幕"**。
出现 0.00% 时本脚本会**自动**把阈值降到 140 复测一遍并打印两组数（不再需要人工记得这一步）。

⚠️ 这个判据只数"字幕带里的亮像素"，**分不出真字和豆腐块**：字体不支持中文时，
PIL 会把每个汉字画成缺字方框，本脚本照样给出非零峰值 → 假通过。
所以交付前必须另跑 `python scripts/doctor.py`（它会真的渲染"中/永"两个字来验字体），
见 SKILL §5 #45 与 §8 第 14 条。
"""
import io
import os
import subprocess
import sys

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # 提示里带中文歌词，避免控制台编码把字弄乱
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _mvcfg import FFMPEG, FFPROBE, MV_TMP, NO_WIN  # noqa: E402

THR = 180  # 2026-09-24：暖木色/暖墨色字幕最暗通道 ~158，180 会假报「没有字幕」，可用第 4 个参数下调
AUTO_FALLBACK_THR = 140  # 出现 0.00% 时自动复测的阈值（§7.4）


def video_duration(video):
    """成片时长；拿不到返回 None（不因此判失败，只是没法判"cue 超出片长"）。"""
    try:
        r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", video],
                           capture_output=True, text=True, creationflags=NO_WIN)
        return float(r.stdout.strip())
    except Exception:
        return None


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


def band_ratio(video, t, cy, half=90, tmp=None, thr=None):
    """抽 t 秒的单帧，量字幕带里的亮像素占比。返回 -1.0 表示**抽帧失败**（不要当成 0%）。"""
    tmp = tmp or os.path.join(MV_TMP, "_qa_caption.jpg")
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    # 先删旧图：否则 ffmpeg 抽帧失败时会拿到上一轮的残留图，得出一个假结论
    if os.path.exists(tmp):
        os.remove(tmp)
    r = subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", "%.3f" % t, "-i", video,
                        "-frames:v", "1", "-q:v", "2", tmp], check=False,
                       creationflags=NO_WIN)
    if r.returncode != 0 or not os.path.exists(tmp):
        return -1.0
    im = np.asarray(Image.open(tmp).convert("RGB"))
    band = im[max(0, cy - half):cy + half]
    bright = (band.min(axis=2) > (THR if thr is None else thr))
    return float(bright.mean() * 100)


def main():
    global THR
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    min_bright = 0.05
    if "--min-bright" in sys.argv:
        min_bright = float(sys.argv[sys.argv.index("--min-bright") + 1])
    video, srt = argv[0], argv[1]
    cy = int(argv[2]) if len(argv) > 2 else 1580
    if len(argv) > 3:
        THR = int(argv[3])
    cues = parse_srt(srt)
    dur = video_duration(video)
    print("%d cues（阈值 %d，判定下限 %.2f%%，成片 %.2fs）"
          % (len(cues), THR, min_bright, dur if dur is not None else -1))
    vals, failed, beyond, checked = [], [], [], []
    for i, (s, e, txt) in enumerate(cues, 1):
        mid = (s + e) / 2
        # cue 落在成片时长之外（例如 --until 只合成了一段）→ 跳过，不当成漏字
        if dur is not None and mid > dur - 0.05:
            beyond.append(i)
            print("cue %-2d %7.2f-%7.2f  跳过（超出成片时长 %.2fs）  %s" % (i, s, e, dur, txt[:22]))
            continue
        r = band_ratio(video, mid, cy)
        checked.append(i)
        if r < 0:
            failed.append(i)
        print("cue %-2d %7.2f-%7.2f  bright=%5.2f%%  %s"
              % (i, s, e, r, txt[:22]))
        # 低于判定下限就自动降阈值复测一次（暖色字幕、结尾淡出段都会让默认阈值假报 0）
        if 0 <= r < min_bright and THR > AUTO_FALLBACK_THR:
            r2 = band_ratio(video, mid, cy, thr=AUTO_FALLBACK_THR)
            print("        阈值 %d 下只有 %.2f%%，自动降到 %d 复测 = %.2f%%（§7.4）——以复测值为准"
                  % (THR, r, AUTO_FALLBACK_THR, r2))
            r = max(r, r2)
        vals.append(r)
    # 无字幕段：取每两个 cue 之间的中点（间隔 >0.6s 的）
    gaps = []
    for i in range(len(cues) - 1):
        a, b = cues[i][1], cues[i + 1][0]
        if b - a > 0.6 and (dur is None or (a + b) / 2 <= dur - 0.05):
            gaps.append(((a + b) / 2, a, b))
    if cues and cues[0][0] > 1.0:
        gaps.append((cues[0][0] / 2, 0.0, cues[0][0]))
    print("--- 无字幕段（应接近 0）---")
    gvals = []
    for t, a, b in gaps:
        r = band_ratio(video, t, cy)
        gvals.append(r)
        print("gap %7.2f (%7.2f-%7.2f)  bright=%5.2f%%" % (t, a, b, r))
    good = [v for v in vals if v >= 0]
    print("SUMMARY 已检 cue n=%d mean=%.2f min=%.2f | 超出片长跳过 %d | gaps n=%d mean=%.3f max=%.3f"
          % (len(vals), float(np.mean(good)) if good else -1, float(np.min(good)) if good else -1,
             len(beyond), len(gvals), float(np.mean(gvals)) if gvals else -1,
             float(np.max(gvals)) if gvals else -1))

    if failed:
        print("\n判定：抽帧失败 %d 条（cue %s）——视频路径/编码或 ffmpeg 有问题，先解决再判定。"
              % (len(failed), ",".join(str(i) for i in failed)))
        return 2
    if not vals:
        print("\n判定：没有一条 cue 落在成片时长内（成片 %.2fs）——判据不成立，"
              "不要当成通过。检查 SRT 与成片是否同源、或先合成整片。" % (dur or -1))
        return 3
    low = [i for i, v in zip(checked, vals) if v < min_bright]
    if low:
        print("\n判定：cue %s 低于 %.2f%% —— 先按 §7.4 降阈值复测，仍低于阈值才算漏字。"
              % (",".join(str(i) for i in low), min_bright))
        return 1
    print("\n判定：每条已检 cue 都有峰值（%d 条）%s。注意本脚本不认字——字体问题请跑 doctor.py。"
          % (len(vals), "；%d 条超出片长已跳过" % len(beyond) if beyond else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
