# -*- coding: utf-8 -*-
"""环境自检：一次问清"这台机器能不能跑"，而不是跑到一半才发现缺东西。

用法：python scripts/doctor.py
退出码：0 = 就绪（可能带警告）；1 = 有阻塞项

v3.1 新增三类检查（都是"静默出错"类的坑）：

- **平台**：`NO_WIN` 是不是按平台算的（Windows 专有 creationflags 曾让 7 个脚本在 macOS/Linux 崩）；
- **curl**：垫图上传/下载要用它（以前写死 `curl.exe`）；
- **字体真的能画中文**：把"中/永"两个字真渲染一遍再比对位图。找不到 CJK 字体时
  PIL 会退化成内置位图字体、字幕变成缺字方框，而 `qa_captions.py` 只数亮像素，**会假报"有字幕"**。
"""
import importlib
import os
import platform
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _mvcfg import (BASE_URL, CURL, DOTENV, FFMPEG, FFPROBE, FONT_BRUSH,  # noqa: E402
                    MV_TMP, MV_WORK, NO_WIN, font_can_cjk, font_source,
                    get, resolve_font)

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


print("== 平台 ==")
print("  %s %s | Python %s" % (platform.system(), platform.release(), sys.version.split()[0]))
if sys.version_info < (3, 10):
    bad("需要 Python 3.10+")
else:
    ok("版本满足 3.10+")
# 这条检查防的是：把 Windows 专有的 creationflags 带到 macOS/Linux（subprocess 会直接抛 ValueError）
if os.name == "nt":
    ok("NO_WIN=0x%08X（Windows：子进程静默，避免闪控制台窗口）" % NO_WIN)
elif NO_WIN == 0:
    ok("NO_WIN=0（非 Windows：creationflags 必须为 0，否则 subprocess 抛 ValueError）")
else:
    bad("NO_WIN=%r 在非 Windows 平台上是非法的：所有调用子进程的脚本都会崩（§5 #42）" % NO_WIN)

print("== 依赖 ==")
for mod in ("numpy", "PIL"):
    try:
        m = importlib.import_module(mod)
        ok("%s %s" % (mod, getattr(m, "__version__", "?")))
    except Exception as e:
        bad("缺少 %s（pip install numpy Pillow）：%s" % (mod, e))

print("== ffmpeg / curl ==")
for name, exe, hint in (("ffmpeg", FFMPEG, "设 FFMPEG_BIN，或装进 PATH"),
                        ("ffprobe", FFPROBE, "设 FFPROBE_BIN，或装进 PATH"),
                        ("curl", CURL, "装 curl 或设 CURL_BIN（垫图上传/下载要用；只跑 examples 不需要）")):
    found = shutil.which(exe) or (exe if os.path.isfile(exe) else None)
    if not found:
        if name == "curl":
            warn("找不到 %s：%s" % (name, hint))
        else:
            bad("找不到 %s（%s）" % (name, hint))
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

print("== 字体（字幕必须真的能画中文）==")
if FONT_BRUSH and not os.path.isfile(FONT_BRUSH):
    bad("MV_FONT_BRUSH 指向的文件不存在：%s" % FONT_BRUSH)
font_path = resolve_font(FONT_BRUSH)
source = font_source()
if not font_path:
    bad("没找到能画中文的字体：字幕会渲染成缺字方框（豆腐块），而 qa_captions 只数亮像素、"
        "**会假报「有字幕」**。请设 MV_FONT_BRUSH 指向一个 OFL 等可商用授权的中文字体"
        "（思源黑体 / Noto Sans SC / 志莽行书），注意不要随仓库或跨机器分发字体文件")
elif not font_can_cjk(font_path):
    bad("指定的字体渲染不了中文（画的是缺字方框）：%s —— 换一个中文字体" % font_path)
else:
    ok("字幕字体 -> %s（%s）"
       % (font_path, "MV_FONT_BRUSH 指定" if source == "env" else "系统字体自动探测"))
    ok("CJK 渲染自检：'中' 与 '永' 字形不同 → 确实能画中文")
    if source == "auto":
        warn("用的是系统字体：自检/预览可以，正式出片建议把 MV_FONT_BRUSH 指向 OFL 等可商用授权字体"
             "（渲染进视频风险低，**分发字体文件才是真风险**，§5 #5）")

print("== 模型名 ==")
for k, dflt in (("MV_KF_MODEL", "agnes-image-2.1-flash"),
                ("MV_I2I_MODEL", "agnes-image-2.1-flash"),
                ("MV_I2V_MODEL", "agnes-video-v2.0"),
                ("MV_VISION_MODEL", "agnes-3.0-flash")):
    v = get(k, dflt)
    print("  %s = %s" % (k, v))
    # 防的是 .env 行内注释没被剥掉（v3.0 的解析器会把 " # 首帧图像" 一起当成模型名）
    if "#" in v or v != v.strip() or " " in v:
        bad("%s 里带了注释或空格（%r）：.env 的行内注释要独立成行，或升级 _mvcfg.py 的解析" % (k, v))

print("== 上传（只影响走真接口的生成）==")
if get("MV_UPLOAD_DISABLE") == "1":
    print("  MV_UPLOAD_DISABLE=1：本轮禁止上传垫图（离线自检模式）")
else:
    print("  垫图图床：%s" % get("MV_UPLOAD_URL", "https://uguu.se/upload"))
    warn("垫图会上传到该图床（默认匿名公共）：含人脸的关键帧会变成公开可访问的 URL；"
         "介意就把 MV_UPLOAD_URL 指向你自己的图床")

print()
if blockers:
    print("结论：有 %d 项阻塞，先解决再开工。" % len(blockers))
    for b in blockers:
        print("  - " + b)
    sys.exit(1)
print("结论：就绪%s。" % ("（另有 %d 条警告）" % len(warns) if warns else ""))
sys.exit(0)
