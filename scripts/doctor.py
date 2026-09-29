# -*- coding: utf-8 -*-
"""环境自检：一次问清"这台机器能不能跑"，而不是跑到一半才发现缺东西。

用法：python scripts/doctor.py
退出码：0 = 就绪（可能带警告）；1 = 有阻塞项
"""
import importlib
import os
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _mvcfg import (BASE_URL, DOTENV, FFMPEG, FFPROBE, FONT_BRUSH,  # noqa: E402
                    MV_TMP, MV_WORK, get)

blockers = []
warns = []


def ok(msg):
    print("  [OK]   " + msg)


def warn(msg):
    warns.append(msg)
    print("  [警告] " + msg)


def bad(msg):
    blockers.append(msg)
    print("  [阻塞] " + msg)


def _run(argv):
    flags = 0x08000000 if os.name == "nt" else 0
    try:
        r = subprocess.run(argv, capture_output=True, text=True, creationflags=flags)
        line = (r.stdout or r.stderr or "").splitlines()
        return line[0] if line else ""
    except Exception as e:
        return "ERR %s" % e


print("== Python ==")
print("  %s" % sys.version.split()[0])
if sys.version_info < (3, 10):
    bad("需要 Python 3.10+")
else:
    ok("版本满足 3.10+")

print("== 依赖 ==")
for mod in ("numpy", "PIL"):
    try:
        m = importlib.import_module(mod)
        ok("%s %s" % (mod, getattr(m, "__version__", "?")))
    except Exception as e:
        bad("缺少 %s（pip install numpy Pillow）：%s" % (mod, e))

print("== ffmpeg ==")
for name, exe in (("ffmpeg", FFMPEG), ("ffprobe", FFPROBE)):
    found = shutil.which(exe) or (exe if os.path.isfile(exe) else None)
    if not found:
        bad("找不到 %s（设 FFMPEG_BIN/FFPROBE_BIN，或装进 PATH）" % name)
    else:
        ok("%s -> %s | %s" % (name, found, _run([found, "-version"])))

print("== 配置 ==")
print("  .env：%s" % (DOTENV or "（没找到；使用进程环境变量或默认值）"))
print("  AGNES_BASE_URL：%s" % BASE_URL)
if get("AGNES_API_KEY"):
    ok("AGNES_API_KEY 已设置（只检查是否存在，不打印内容）")
else:
    warn("未设置 AGNES_API_KEY：联网的生成/复核步骤需要它；只跑 examples 的示例合成不需要")


print("== 目录 ==")
for label, d in (("MV_WORK", MV_WORK), ("MV_TMP", MV_TMP)):
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".doctor_probe")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        ok("%s 可写：%s" % (label, d))
    except Exception as e:
        bad("%s 不可写：%s（%s）" % (label, d, e))

print("== 字体 ==")
if FONT_BRUSH and os.path.isfile(FONT_BRUSH):
    ok("MV_FONT_BRUSH -> %s" % FONT_BRUSH)
elif FONT_BRUSH:
    bad("MV_FONT_BRUSH 指向的文件不存在：%s" % FONT_BRUSH)
else:
    warn("未设置 MV_FONT_BRUSH：字幕会退回系统字体。正式出片请指定一个 OFL 等可商用授权的字体"
         "（注意：不要随仓库分发字体文件）")

print("== 模型名 ==")
for k, dflt in (("MV_KF_MODEL", "agnes-image-2.1-flash"),
                ("MV_I2I_MODEL", "agnes-image-2.1-flash"),
                ("MV_I2V_MODEL", "agnes-video-v2.0"),
                ("MV_VISION_MODEL", "agnes-3.0-flash")):
    print("  %s = %s" % (k, get(k, dflt)))

print()
if blockers:
    print("结论：有 %d 项阻塞，先解决再开工。" % len(blockers))
    for b in blockers:
        print("  - " + b)
    sys.exit(1)
print("结论：就绪%s。" % ("（另有 %d 条警告）" % len(warns) if warns else ""))
sys.exit(0)
