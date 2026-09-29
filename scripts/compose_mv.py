# -*- coding: utf-8 -*-
"""参考合成器：把逐镜片段按分镜库的时间轴拼成整片，带字幕、图层、暗角颗粒与结尾淡出。

这一版是从真实交付过多首歌的合成器里抽出来的通用版，原本写死的东西全部改成参数：
分镜库 / 片段目录 / 输出 / 音频 / 字幕 / 颜色 / 字体 都走环境变量或命令行。

它保留了两个**别自己重造**的关键设计：

1. **按帧号缓存 JPEG**（`<WORK>/out/%05d.jpg`）——改字幕或改颜色时，只把受影响的帧
   从缓存里**移走**（不要删）再原样重跑，其余帧直接复用。整片 9000 帧能压到 3–5 分钟，
   而 `--fresh` 会全片重画（9000 帧约 40–60 分钟）。**不要随便 --fresh。**
2. **每镜提前 LEAD 秒入场 + 镜界处 DISS 秒真交叉溶解**——按帧号算，可复算、可断点续跑。

用法：
    python compose_mv.py                 # 全片
    python compose_mv.py --until 40      # 只合成前 40 秒自检
    python compose_mv.py --fresh         # 清空帧缓存重画（慎用）

环境变量：
    ZDN_BANK     分镜库 JSON（必填）
    ZDN_CLIPS    片段目录（必填）：里面是 shot_<key>.mp4
    ZDN_OUT      成片输出路径（必填）
    ZDN_SRT      字幕 SRT；给了才画字幕
    ZDN_AUDIO    音轨；给了才混音
    ZDN_WORK     帧缓存目录，默认 <MV_WORK>/compose
    ZDN_TOTAL    成片总时长（秒）；不给则取最后一镜的 t1 + 2
    ZDN_LEAD     每镜提前入场秒数，默认 0.65
    ZDN_DISSOLVE 镜界交叉溶解秒数，默认 0.65
    ZDN_FADE_OUT "起秒,时长" 结尾淡出，如 "295,6"；留空则不淡出
    ZDN_CLAUSES  逐句揭示时间表 JSON（可选）
    ZDN_CAPTION_COLORS  字幕"情绪色"锚点 JSON（可选）
    ZDN_CAP_Y / ZDN_CAP_MAX_W  字幕基线 y / 单行最大宽
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _mvcfg import FFMPEG, FONT_BRUSH, MV_WORK, get  # noqa: E402

try:  # 额外图层（行情网格、界面等）是可选件：没有这个模块就跳过，不影响出片
    import ui_layer  # type: ignore
except Exception:  # pragma: no cover
    ui_layer = None

FPS = 30
W, H = 1080, 1920

BANK = get("ZDN_BANK")
CLIPS_DIR = get("ZDN_CLIPS")
OUT = get("ZDN_OUT")
SRT = get("ZDN_SRT")
AUDIO = get("ZDN_AUDIO")
WORK = get("ZDN_WORK", os.path.join(MV_WORK, "compose"))
CLAUSES_J = get("ZDN_CLAUSES")
LEAD = float(get("ZDN_LEAD", "0.65"))
DISS = float(get("ZDN_DISSOLVE", "0.65"))
CAP_Y = int(get("ZDN_CAP_Y", "1580"))
CAP_MAX_W = int(get("ZDN_CAP_MAX_W", "1000"))
CAP_LH = 104

# 字幕"情绪色"：默认给中性暖白。一首歌一个色板，见 references/prompt-rules.md 的"字幕配色"一节。
NEUTRAL_ANCHORS = [(0.0, (240, 240, 236)), (1e9, (238, 238, 236))]


def _load_color_anchors():
    """色板优先级：分镜库 _meta.caption_colors > ZDN_CAPTION_COLORS 文件 > 中性默认。"""
    raw = None
    if BANK and os.path.isfile(BANK):
        raw = (json.load(open(BANK, encoding="utf-8")).get("_meta") or {}).get("caption_colors")
    if raw is None and get("ZDN_CAPTION_COLORS"):
        raw = json.load(open(get("ZDN_CAPTION_COLORS"), encoding="utf-8"))
    if not raw:
        return NEUTRAL_ANCHORS
    return [(float(t), tuple(c)) for t, c in raw]


ANCHORS = _load_color_anchors()


def cap_color(t):
    if t <= ANCHORS[0][0]:
        return ANCHORS[0][1]
    for (t0, c0), (t1, c1) in zip(ANCHORS, ANCHORS[1:]):
        if t0 <= t < t1:
            k = (t - t0) / max(t1 - t0, 1e-6)
            return tuple(int(round(a + (b - a) * k)) for a, b in zip(c0, c1))
    return ANCHORS[-1][1]


def parse_srt(path):
    cues = []
    for block in open(path, encoding="utf-8-sig").read().replace("\r", "").split("\n\n"):
        lines = block.strip().split("\n")
        if len(lines) < 2 or "-->" not in lines[1]:
            continue
        a, b = lines[1].split("-->")

        def to_sec(s):
            h, m, sec = s.strip().split(":")[:3]
            return int(h) * 3600 + int(m) * 60 + float(sec.replace(",", "."))
        cues.append((to_sec(a), to_sec(b), " ".join(lines[2:]).strip()))
    return cues


_yy, _xx = np.mgrid[0:H, 0:W]
_R = np.sqrt(((_xx - W / 2) / (W / 2)) ** 2 + ((_yy - H / 2) / (H / 2)) ** 2)
_VIG = 1 - 0.10 * np.clip(_R - 0.55, 0, 1) ** 1.5
_NOISE = np.random.default_rng(13).normal(0, 1.0, (H, W, 1)).astype(np.float32)


def vignette_grain(img):
    arr = np.asarray(img).astype(np.float32) * _VIG[..., None]
    return Image.fromarray(np.clip(arr + _NOISE, 0, 255).astype(np.uint8), "RGB")


_fonts = {}
_FONT_FALLBACK = ["NotoSansSC-VF.ttf", "msyh.ttc", "arial.ttf", "DejaVuSans.ttf"]


def _font_path():
    if FONT_BRUSH and os.path.isfile(FONT_BRUSH):
        return FONT_BRUSH
    roots = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
             "/usr/share/fonts", "/usr/local/share/fonts", "/Library/Fonts"]
    for name in _FONT_FALLBACK:
        for root in roots:
            for sub in ("", "truetype", "opentype"):
                p = os.path.join(root, sub, name)
                if os.path.isfile(p):
                    return p
    return None


_FONT_PATH = _font_path()


def brush(size):
    if size not in _fonts:
        if _FONT_PATH:
            _fonts[size] = ImageFont.truetype(_FONT_PATH, size)
        else:
            print("警告：没找到可用字体，字幕将用 PIL 内置位图字体（只适合自检）。"
                  "请设 MV_FONT_BRUSH 指向一个 OFL 等可商用的行书/黑体字体。", flush=True)
            _fonts[size] = ImageFont.load_default()
    return _fonts[size]


def draw_row(overlay, txt, y, alpha, t):
    size = 78
    color = cap_color(t)
    f = brush(size)
    tw0 = f.getlength(txt)
    if tw0 > CAP_MAX_W:
        size = max(46, int(size * CAP_MAX_W / max(tw0, 1)))
        f = brush(size)
    bbox = f.getbbox(txt)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pad_x, pad_y = 46, 26
    ImageDraw.Draw(lay).rounded_rectangle(
        [W / 2 - tw / 2 - pad_x, y - th / 2 - pad_y,
         W / 2 + tw / 2 + pad_x, y + th / 2 + pad_y],
        radius=18, fill=(6, 10, 14, int(120 * alpha)))
    lay = lay.filter(ImageFilter.GaussianBlur(9))
    text = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(text).text((W / 2, y), txt, font=f, fill=(*color, int(255 * alpha)),
                              anchor="mm", stroke_width=1, stroke_fill=(*color, int(255 * alpha)))
    shadow = text.filter(ImageFilter.GaussianBlur(7))
    glow = Image.new("RGBA", (W, H), (*color, int(60 * alpha)))
    glow.putalpha(text.getchannel("A").point(lambda v: int(v * 0.42)))
    glow = glow.filter(ImageFilter.GaussianBlur(13))
    overlay.alpha_composite(lay)
    overlay.alpha_composite(shadow, (0, 4))
    overlay.alpha_composite(Image.alpha_composite(glow, text))


def draw_caption(overlay, txt, t, s, e, clauses=None):
    """逐句揭示：到点才出现，正在唱的那一行最亮，唱过的压暗。"""
    if clauses:
        n = len(clauses)
        cur = max([k for k, c in enumerate(clauses) if t >= c[1]], default=-1)
        for k, (ctext, cs, ce) in enumerate(clauses):
            if t < cs:
                continue
            alpha = (min(1.0, (t - cs) / 0.45) * min(1.0, max(0.0, (e - t) / 0.35))
                     * (1.0 if k == cur else 0.78))
            if alpha > 0.01:
                draw_row(overlay, ctext, CAP_Y + (k - (n - 1) / 2.0) * CAP_LH, alpha, t)
        return
    ph = (t - s) / max(e - s, 0.01)
    alpha = min(1.0, ph / 0.055) * min(1.0, (1 - ph) / 0.07)
    if alpha > 0.01:
        draw_row(overlay, txt, CAP_Y, alpha, t)


def load_frame(clip_frames, key, local_fps):
    """取该镜"镜头内第几帧"。超出素材长度只做轻微放大兜底（上限 1.18×）。"""
    outd, n = clip_frames[key]
    if int(local_fps) < n:
        return Image.open(os.path.join(outd, "%04d.jpg" % (int(local_fps) + 1))).convert("RGB")
    zoom = min(1.18, 1.0 + 0.012 * (local_fps - (n - 1)))
    nw, nh = int(W / zoom), int(H / zoom)
    img = Image.open(os.path.join(outd, "%04d.jpg" % n)).convert("RGB")
    return img.crop(((W - nw) // 2, (H - nh) // 2,
                     (W - nw) // 2 + nw, (H - nh) // 2 + nh)).resize((W, H), Image.LANCZOS)


def main():
    for name, val in (("ZDN_BANK", BANK), ("ZDN_CLIPS", CLIPS_DIR), ("ZDN_OUT", OUT)):
        if not val:
            sys.exit("缺少 %s（见本文件顶部说明与 .env.example）" % name)

    bank = json.load(open(BANK, encoding="utf-8"))
    all_shots = sorted(bank["shots"], key=lambda s: s["t0"])
    total = float(get("ZDN_TOTAL") or (all_shots[-1].get("t1") or all_shots[-1]["t0"] + 2))
    until = total
    if "--until" in sys.argv:
        until = float(sys.argv[sys.argv.index("--until") + 1])

    shots = [s for s in all_shots if s["t0"] < until]
    SEGS = []
    for i, s in enumerate(shots):
        t1 = min(shots[i + 1]["t0"] if i + 1 < len(shots) else until, until)
        SEGS.append((s["t0"], t1, s["key"], s, (LEAD if i > 0 else 0.0)))

    cues = parse_srt(SRT) if (SRT and os.path.isfile(SRT)) else []
    cue_clauses = {}
    if CLAUSES_J and os.path.exists(CLAUSES_J):
        for c in json.load(open(CLAUSES_J, encoding="utf-8"))["cues"]:
            cue_clauses[round(c["start"], 2)] = (c.get("eff_start", c["start"]),
                                                 c.get("eff_end", c["end"]),
                                                 c.get("clauses"))
        print("逐句揭示已启用：%d 条 cue" % len(cue_clauses), flush=True)
    print("shots:", len(SEGS), "| cues:", len(cues), "| until %.2fs" % until, flush=True)

    clip_frames = {}
    for t0, t1, key, s, lead in SEGS:
        src = os.path.join(CLIPS_DIR, "shot_%s.mp4" % key)
        # 2 KB 以下基本是空文件或坏下载；上界不设，因为静态镜的正经素材也可能很小
        if not os.path.exists(src) or os.path.getsize(src) < 2000:
            sys.exit("MISSING %s %s" % (key, src))
        outd = os.path.join(WORK, "frames", key)
        os.makedirs(outd, exist_ok=True)
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", src,
                        "-vf", "scale=%d:%d:force_original_aspect_ratio=decrease,"
                               "pad=%d:%d:(ow-iw)/2:(oh-ih)/2,fps=%d" % (W, H, W, H, FPS),
                        "-q:v", "3", os.path.join(outd, "%04d.jpg")], check=False)
        clip_frames[key] = (outd, len([x for x in os.listdir(outd) if x.endswith(".jpg")]))

    def seg_at(t):
        for seg in SEGS:
            if seg[0] <= t < seg[1]:
                return seg
        return SEGS[-1]

    def soff(shot):
        """src_offset：跳过素材开头那一小段（解剖畸形常集中在开头）。缺省 0 ＝ 旧行为。"""
        return float(shot.get("src_offset", 0) or 0)

    out_dir = os.path.join(WORK, "out")
    os.makedirs(out_dir, exist_ok=True)
    if "--fresh" in sys.argv:
        shutil.rmtree(out_dir, ignore_errors=True)
        os.makedirs(out_dir, exist_ok=True)
        print("fresh: 已清空 out 帧缓存", flush=True)

    for f in range(int(until * FPS)):
        t = f / FPS
        fp = os.path.join(out_dir, "%05d.jpg" % f)
        if os.path.exists(fp):          # 帧号复用：这就是"定点返修只重画几十帧"的机制
            continue
        st0, st1, key, shot, lead = seg_at(t)
        base = load_frame(clip_frames, key, (t - st0 + lead + soff(shot)) * FPS)
        if st1 < until - 0.01 and st1 - t < DISS:
            n0, _, keyn, shotn, leadn = seg_at(st1 + 0.001)
            base = Image.blend(
                base, load_frame(clip_frames, keyn, (t - n0 + leadn + soff(shotn)) * FPS),
                max(0.0, min(1.0, (t - (st1 - DISS)) / DISS)))
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if ui_layer is not None and (shot.get("ui") or {}):
            ov = ui_layer.render_overlay(shot.get("ui") or {}, key, t - st0, st1 - st0)
            if ov is not None:
                overlay.alpha_composite(ov)
        for s, e, txt in cues:
            cs, ce, cl = cue_clauses.get(round(s, 2), (s, e, None))
            if max(cs, 1.0) <= t < ce and cs < until - 0.05:
                draw_caption(overlay, txt.replace(" ", "").strip(), t, cs, ce, cl)
        comp = vignette_grain(Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB"))
        comp.save(fp, quality=88)
        if f % 600 == 0:
            print("frame %d/%d" % (f, int(until * FPS)), flush=True)

    cmd = [FFMPEG, "-y", "-framerate", str(FPS), "-i", os.path.join(out_dir, "%05d.jpg")]
    if AUDIO and os.path.exists(AUDIO):
        cmd += ["-i", AUDIO, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-t", "%.3f" % until]
    fade_out = (get("ZDN_FADE_OUT", "") or "").strip()
    if fade_out:
        fs, fd = [float(x) for x in fade_out.split(",")]
        cmd += ["-vf", "fade=t=out:st=%.3f:d=%.3f" % (fs, fd)]
    cmd += [OUT]
    subprocess.run(cmd, check=True)
    print("MV DONE:", OUT, flush=True)


if __name__ == "__main__":
    main()
