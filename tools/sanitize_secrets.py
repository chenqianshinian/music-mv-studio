# -*- coding: utf-8 -*-
"""把仓库里的「明文密钥 / 从别的文件偷读密钥」改成读环境变量。

为什么单独做成一个脚本：2026-09-29 发布前扫描发现，本地工作目录的
`gen_zuindongni.py` 第 20 行有明文 KEY，而 `ask_image.py`／`ask_multi.py` 又是
用正则从 `dense_scan_v3.py` 里「偷读」KEY 的。这类东西一旦跟着仓库上传就是事故，
所以做成一个可重复执行、可当 CI 门禁的脚本。

本脚本**不会打印任何密钥内容**，只报告改了几处。
用法：python tools/sanitize_secrets.py [--dry-run]
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 注意：下面这些模式都是拼出来的，避免脚本自身被自己的扫描规则命中。
SK_PATTERN = re.compile("^" + r"KEY\s*=\s*[\"']" + "sk" + "-" + r"[^\"']+[\"']\s*$", re.M)
STEAL_PATTERN = re.compile(
    r"src\s*=\s*io\.open\(os\.path\.join\(WORK,\s*[\"']dense_scan_v3\.py[\"']\).*?"
    r"KEY\s*=\s*re\.search\(.*?\)\.group\(1\)",
    re.M | re.S)

ENV_LINE = ('KEY = os.environ.get("AGNES_API_KEY") or ""   '
            '# 发布版：密钥只走环境变量，禁止写进仓库')


def main():
    dry = "--dry-run" in sys.argv
    for base, _dirs, files in os.walk(os.path.join(ROOT, "music-mv-studio", "scripts")):
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(base, name)
            text = io.open(path, encoding="utf-8").read()
            touched = SK_PATTERN.sub(ENV_LINE, text)
            touched = STEAL_PATTERN.sub(ENV_LINE, touched)
            if touched == text:
                continue
            print("  %-22s 需要改（明文 KEY 或偷读块）" % name)
            if not dry:
                io.open(path, "w", encoding="utf-8").write(touched)
    print("（dry-run，未落盘）" if dry else "已改写：请再跑 tools/hygiene_scan.py 复查")


if __name__ == "__main__":
    main()
