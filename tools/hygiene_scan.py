# -*- coding: utf-8 -*-
"""发布门禁：扫「明文密钥」与「个人/机器绝对路径」。

用法：python tools/hygiene_scan.py
退出码：0 = 干净；1 = 发现问题（CI 里直接用这个当门槛）
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".git", "__pycache__", "node_modules"}
TEXT_EXT = {".md", ".py", ".json", ".yaml", ".yml", ".txt", ".toml", ".cfg", ".example", ""}

CHECKS = [
    ("明文密钥(sk-…)", re.compile("sk" + "-" + r"[A-Za-z0-9]{12,}")),
    ("明文密钥(Bearer …)", re.compile(r"Bearer\s+[A-Za-z0-9._-]{16,}")),
    ("机器路径(Windows 用户名)", re.compile(r"C:\\+Users\\+[A-Za-z0-9_.-]+")),
    ("机器路径(个人盘)", re.compile(r"[A-Z]:\\+MV-temp|[A-Z]:\\+CodexMemory|[A-Z]:\\+om-setup")),
    ("个人歌库路径", re.compile(r"[A-Z]:\\+AIGC")),
]


def main():
    bad = 0
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if os.path.splitext(name)[1].lower() not in TEXT_EXT and name != ".gitignore":
                continue
            path = os.path.join(base, name)
            try:
                text = io.open(path, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            for label, pattern in CHECKS:
                for m in pattern.finditer(text):
                    line = text[: m.start()].count("\n") + 1
                    rel = os.path.relpath(path, ROOT)
                    if label.startswith("明文密钥"):
                        print("  [命中] %-22s %s:%d  内容不打印" % (label, rel, line))
                    else:
                        print("  [命中] %-22s %s:%d  %s" % (label, rel, line, m.group(0)))
                    bad += 1
    print("扫描完毕：%d 处需要处理" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
