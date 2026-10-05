# -*- coding: utf-8 -*-
"""所有脚本共用的配置入口：路径、密钥、**平台差异**一律走这里，代码里不留个人路径与 Windows 专有常量。

优先级：**进程环境变量 > 仓库根目录的 .env > 下面的安全默认值**。
所以换一台机器不需要改代码，只改一份 .env。

v3.1 补齐的三件事（都是真实踩过的，见 SKILL §5 #42–#45）：

1. **平台差异集中在 `NO_WIN`**：CREATE_NO_WINDOW（`0x0800_0000`）这个 creationflags 只在 Windows 有效，
   在 macOS/Linux 上传给 `subprocess` 会直接抛 `ValueError: creationflags is only supported
   on Windows platforms`——7 个脚本会一起崩（`qa_captions.py` 就在 README 的"5 分钟跑通"里）。
   另外 `curl.exe` / `ffprobe.exe` / `NUL` 也都是 Windows 专有，统一走 `CURL` / `FFPROBE` / `NULL_DEVICE`。
2. **`.env` 要剥行内注释**：`MV_KF_MODEL=agnes-image-2.1-flash  # 首帧` 里那段注释不能进模型名，
   否则照 README 第一步 `cp .env.example .env` 就会把注释当模型名发给接口。
3. **字体要跨平台找得到 CJK，并且能验证它真的能画中文**：找不到时 PIL 会退化成内置位图字体，
   中文全变豆腐块，而 `qa_captions.py` 只数字幕带的亮像素，会**假报"有字幕"**。
   `resolve_font()` 负责找，`font_can_cjk()` 负责用"两个不同汉字渲染结果是否完全相同"来证伪
   （缺字时都画成同一个 .notdef 方框 → 位图完全相同）。

支持的变量（模板见仓库根 `.env.example`）：

  AGNES_API_KEY     接口密钥；只有真正要联网的脚本才要求它
  AGNES_BASE_URL    接口基址，默认 https://apihub.agnes-ai.cn
  MV_KF_MODEL / MV_I2I_MODEL / MV_I2V_MODEL / MV_VISION_MODEL
  FFMPEG_BIN        ffmpeg 可执行文件，默认 "ffmpeg"（走 PATH）
  FFPROBE_BIN       ffprobe；默认取 FFMPEG_BIN 同目录下的 ffprobe
  CURL_BIN          curl 可执行文件，默认 "curl"（Windows 10+ 自带 curl.exe，同样是 curl）
  MV_WORK           中间产物根目录（逐镜抽帧缓存、日志），默认 <当前目录>/work
  MV_TMP            临时目录，默认 <当前目录>/tmp
  MV_FONT_BRUSH     行书/黑体字幕字体（**正式出片必须用 OFL 等可商用授权字体**），可选
  MV_FONT_UI        界面/图注字体，可选
  MV_UPLOAD_URL     生成器上传垫图的图床地址，默认 https://uguu.se/upload
  MV_UPLOAD_FIELD   图床表单字段名，默认 files[]
  MV_UPLOAD_DISABLE 设为 1 时禁止上传（离线自检用；到上传那一步直接报错，而不是静默失败）
"""
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


def _strip_inline_comment(v):
    """剥掉 ` #注释`；只认"空白 + #"，避免误伤值里本来就有的 #（例如带锚点的路径）。"""
    m = re.search(r"\s#", v)
    return (v[: m.start()] if m else v).strip()


def _load_dotenv():
    """把最近的 .env 读进 os.environ（已存在的变量不覆盖）。"""
    d = _HERE
    for _ in range(3):
        p = os.path.join(d, ".env")
        if os.path.isfile(p):
            for raw in open(p, encoding="utf-8-sig"):
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = _strip_inline_comment(v).strip('"').strip("'")
                os.environ.setdefault(k.strip(), v)
            return p
        d = os.path.dirname(d)
    return None


DOTENV = _load_dotenv()


def get(name, default=None):
    """取环境变量；空串按"没设"处理。"""
    v = os.environ.get(name)
    return default if v in (None, "") else v


def api_key():
    """需要联网的脚本调用它取密钥；没有就给出可照做的报错。"""
    k = get("AGNES_API_KEY")
    if not k:
        sys.exit("未设置 AGNES_API_KEY：把仓库根的 .env.example 复制成 .env 并填写密钥后重试"
                 "（也可以直接设进程环境变量）。")
    return k


BASE_URL = get("AGNES_BASE_URL", "https://apihub.agnes-ai.cn").rstrip("/")
FFMPEG = get("FFMPEG_BIN", "ffmpeg")
CURL = get("CURL_BIN", "curl")
NULL_DEVICE = os.devnull
# 子进程静默：Windows 下避免 curl/ffprobe/ffmpeg 各自闪一个控制台窗口；其它平台必须是 0
NO_WIN = 0x08000000 if os.name == "nt" else 0


def _probe_default():
    d = os.path.dirname(FFMPEG)
    # Windows 上 FFMPEG_BIN 常写成 ffmpeg.exe，此时默认的兄弟程序也要带 .exe
    exe = "ffprobe" + (".exe" if FFMPEG.lower().endswith(".exe") else "")
    return os.path.join(d, exe) if d else exe


FFPROBE = get("FFPROBE_BIN", _probe_default())
MV_WORK = get("MV_WORK", os.path.join(os.getcwd(), "work"))
MV_TMP = get("MV_TMP", os.path.join(os.getcwd(), "tmp"))
FONT_BRUSH = get("MV_FONT_BRUSH")
FONT_UI = get("MV_FONT_UI")

# ── 字体：跨平台候选表 ────────────────────────────────────────────────────
# 顺序＝优先级。Windows 用微软雅黑/思源，macOS 用苹方/黑体，Linux 用 Noto/文泉驿。
# ⚠️ 这些是**系统字体**：渲染进视频风险低，但**分发字体文件才是真风险**——
#    正式出片请把 MV_FONT_BRUSH 指向自己的 OFL 等可商用授权字体（见 SKILL §5 #5）。
_FONT_DIRS = {
    "nt": [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
           os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts")],
    "darwin": ["/System/Library/Fonts", "/System/Library/Fonts/Supplemental",
               "/Library/Fonts", os.path.expanduser("~/Library/Fonts")],
}
_FONT_DIRS["posix"] = ["/usr/share/fonts", "/usr/local/share/fonts",
                       os.path.expanduser("~/.fonts"), os.path.expanduser("~/.local/share/fonts")]

_FONT_NAMES = [
    # macOS / 泛用
    "PingFang.ttc", "Hiragino Sans GB.ttc", "STHeiti Medium.ttc", "Songti.ttc",
    "Arial Unicode.ttf",
    # Windows
    "NotoSansSC-VF.ttf", "msyh.ttc", "msyhbd.ttc", "simhei.ttf", "simsun.ttc",
    # Linux
    "NotoSansCJK-Regular.ttc", "NotoSansCJKsc-Regular.otf", "NotoSerifCJK-Regular.ttc",
    "wqy-zenhei.ttc", "wqy-microhei.ttc", "DroidSansFallbackFull.ttf",
]
_FONT_SUBS = ("", "truetype", "opentype", "truetype/noto", "opentype/noto",
              "truetype/arphic", "truetype/wqy", "truetype/dejavu")


def _font_dirs():
    if os.name == "nt":
        return _FONT_DIRS["nt"]
    if sys.platform == "darwin":
        return _FONT_DIRS["darwin"]
    return _FONT_DIRS["posix"] + _FONT_DIRS["darwin"]


def font_can_cjk(path):
    """这个字体**真的**能画中文吗？

    判据：同一个字体渲染两个不同汉字（中 / 永）。缺字时两字都画成同一个 .notdef 方框 →
    位图完全相同 → 判为不支持。这样能把"真有 CJK 字形"和"画方框的拉丁字体"分开。
    """
    if not path or not os.path.isfile(path):
        return False
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return True  # 没有 Pillow 就不猜；doctor.py 会单独报缺依赖
    try:
        img_a, img_b = Image.new("L", (64, 64), 0), Image.new("L", (64, 64), 0)
        ImageDraw.Draw(img_a).text((6, 2), "中", font=ImageFont.truetype(path, 48), fill=255)
        ImageDraw.Draw(img_b).text((6, 2), "永", font=ImageFont.truetype(path, 48), fill=255)
    except Exception:
        return False
    return img_a.tobytes() != img_b.tobytes() and max(img_a.getdata()) > 0


def resolve_font(prefer=None):
    """找一个**能画中文**的字体文件；找不到返回 None。

    显式设了 MV_FONT_BRUSH 时优先用它（哪怕它画不了中文——那是用户的选择，
    doctor.py 会把"画不了"报成阻塞项，而不是在这里偷偷换掉）。
    """
    if prefer and os.path.isfile(prefer):
        return prefer
    for root in _font_dirs():
        for sub in _FONT_SUBS:
            for name in _FONT_NAMES:
                p = os.path.join(root, sub, name) if sub else os.path.join(root, name)
                if os.path.isfile(p) and font_can_cjk(p):
                    return p
    return None


FONT_AUTO = resolve_font(FONT_BRUSH)


def font_source():
    """字幕字体来自哪：'env'（用户指定）/ 'auto'（系统字体兜底）/ None（没找到）。"""
    if FONT_BRUSH and os.path.isfile(FONT_BRUSH):
        return "env"
    return "auto" if FONT_AUTO else None
