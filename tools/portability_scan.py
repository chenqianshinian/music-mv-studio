# -*- coding: utf-8 -*-
"""发布门禁（跨平台）：扫出**只在 Windows 上能跑**的写法。

为什么要有这条门禁：v3.0 的脚本在 Windows 上一切正常，但同一份代码在 macOS/Linux 上
有 7 个脚本直接崩（`creationflags=0x08000000` 传给 subprocess → ValueError），
生成器还写死了 `curl.exe` / `ffprobe.exe` / `NUL`。这些都不会在 Windows 的 CI 上暴露，
所以必须由一条静态门禁 + 一条**在 Linux/macOS 上真跑管线**的冒烟测试（tests/smoke_offline.py）来兜。

用法：python tools/portability_scan.py
退出码：0 = 干净；1 = 命中（CI 里直接用这个当门槛）
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".git", "__pycache__", "node_modules", "demo", "work", "tmp"}
# 只扫**代码与配置**：文档（.md/.txt）里会引用反例（比如 §5 #42 就在讲"不要写 NUL"），
# 把它们一起扫会逼着我们在文档里塞豁免标记，反而没人看。文档里的命令靠人工复核。
TEXT_EXT = {".py", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".example",
            ".sh", ".bash", ".zsh", ".bat", ".cmd", ".ps1", ""}

# 允许出现这些写法的文件：本门禁自身（正则里必然含关键字）
SELF = {os.path.join("tools", "portability_scan.py")}
# 豁免标记：写在命中行**或它上一行**都算（长正则在上一行写注释更好读）
ALLOW_LINE = re.compile(r"portability-scan-allow")

CHECKS = [
    # 只在 Windows 有效的 creationflags（必须走 _mvcfg.NO_WIN）
    ("Windows 专有 creationflags", re.compile(r"creationflags\s*=\s*0x0*8000000")),
    # 写死的 .exe 可执行名（走 FFMPEG_BIN/FFPROBE_BIN/CURL_BIN 才对）
    ("写死的 .exe 调用", re.compile(r"[\"'](?:curl|ffmpeg|ffprobe|python|py)\.exe[\"']")),
    # Windows 的空设备名（跨平台要 os.devnull）
    ("Windows 空设备 NUL", re.compile(r"[\"']NUL[\"']")),
    # 反斜杠路径分隔（跨平台要 os.path.join / os.sep）
    ("写死的 Windows 盘符路径", re.compile(r"[\"'][A-Za-z]:\\\\")),
    # 只在 Windows 可用的 shell 惯用法
    ("Windows 专有命令", re.compile(r"\b(?:powershell|cmd\.exe|cls|copy\s+/y|del\s+/[fq])\b", re.I)),
]


def main():
    bad = 0
    files = 0
    for base, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            if os.path.splitext(name)[1].lower() not in TEXT_EXT and name != ".gitignore":
                continue
            path = os.path.join(base, name)
            rel = os.path.relpath(path, ROOT)
            if rel in SELF:
                continue
            try:
                lines = io.open(path, encoding="utf-8", errors="ignore").read().splitlines()
            except OSError:
                continue
            files += 1
            for i, line in enumerate(lines, 1):
                prev = lines[i - 2] if i > 1 else ""
                if ALLOW_LINE.search(line) or ALLOW_LINE.search(prev):
                    continue
                for label, pattern in CHECKS:
                    m = pattern.search(line)
                    if m:
                        print("  [命中] %-24s %s:%d  %s" % (label, rel, i, m.group(0)))
                        bad += 1
    print("扫描 %d 个文本文件完毕：%d 处只在 Windows 上能跑的写法" % (files, bad))
    if bad:
        print("修法：跨平台常量与可执行文件走 scripts/_mvcfg.py 的 "
              "NO_WIN / FFMPEG / FFPROBE / CURL / NULL_DEVICE（见 SKILL §5 #42）。")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
