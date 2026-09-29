# -*- coding: utf-8 -*-
"""所有脚本共用的配置入口：路径与密钥一律走环境变量，代码里不留任何个人路径。

优先级：**进程环境变量 > 仓库根目录的 .env > 下面的安全默认值**。
所以换一台机器不需要改代码，只改一份 .env。

支持的变量（模板见仓库根 `.env.example`）：

  AGNES_API_KEY     接口密钥；只有真正要联网的脚本才要求它
  AGNES_BASE_URL    接口基址，默认 https://apihub.agnes-ai.cn
  FFMPEG_BIN        ffmpeg 可执行文件，默认 "ffmpeg"（走 PATH）
  FFPROBE_BIN       ffprobe；默认取 FFMPEG_BIN 同目录下的 ffprobe
  MV_WORK           中间产物根目录（逐镜抽帧缓存、日志），默认 <当前目录>/work
  MV_TMP            临时目录，默认 <当前目录>/tmp
  MV_FONT_BRUSH     行书字幕字体（必须 OFL 等可商用授权），可选
  MV_FONT_UI        界面/图注字体，可选
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


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
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
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


def _probe_default():
    d = os.path.dirname(FFMPEG)
    exe = "ffprobe.exe" if FFMPEG.lower().endswith(".exe") else "ffprobe"
    return os.path.join(d, exe) if d else exe


FFPROBE = get("FFPROBE_BIN", _probe_default())
MV_WORK = get("MV_WORK", os.path.join(os.getcwd(), "work"))
MV_TMP = get("MV_TMP", os.path.join(os.getcwd(), "tmp"))
FONT_BRUSH = get("MV_FONT_BRUSH")
FONT_UI = get("MV_FONT_UI")
