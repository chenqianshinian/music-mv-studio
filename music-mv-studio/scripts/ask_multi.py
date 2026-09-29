# -*- coding: utf-8 -*-
"""把多张图放进同一条提问里，让视觉模型做**对比**判断（ask_batch 是逐张单独问）。

用法：python ask_multi.py <输出txt> "<问题>" <图1> [<图2> ...]
图片按给出顺序标为 图1..图N。
"""
import base64
import io
import json
import os
import re
import sys
import time
import urllib.request

from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK = r"C:\Users\Huangzelong\Documents\Codex\2026-09-09\ni\work"
KEY = re.search(r'KEY\s*=\s*"([^"]+)"',
                io.open(os.path.join(WORK, "dense_scan_v3.py"), encoding="utf-8").read()).group(1)


def data_url(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    im = im.resize((768, int(768 * h / w)), Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def main():
    out, question, imgs = sys.argv[1], sys.argv[2], sys.argv[3:]
    content = [{"type": "text",
                "text": question + "\n下面按顺序给出 %d 张图，依次记为 图1..图%d。" % (len(imgs), len(imgs))}]
    for p in imgs:
        content.append({"type": "image_url", "image_url": {"url": data_url(p)}})
    body = {"model": "agnes-3.0-flash", "max_tokens": 800,
            "messages": [{"role": "user", "content": content}]}
    ans = "(FAILED)"
    for a in range(5):
        try:
            rq = urllib.request.Request(
                "https://apihub.agnes-ai.cn/v1/chat/completions",
                data=json.dumps(body).encode(),
                headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
            d = json.loads(urllib.request.urlopen(rq, timeout=180).read().decode())
            m = d["choices"][0]["message"]
            ans = (m.get("content") or m.get("reasoning_content") or "").strip()
            break
        except Exception as e:
            sys.stderr.write("retry %s\n" % e)
            time.sleep(5 + a * 7)
    with io.open(out, "w", encoding="utf-8") as f:
        f.write("Q: %s\nIMGS: %s\n\n%s\n" % (question, ", ".join(imgs), ans))
    sys.stdout.write(ans + "\n")


if __name__ == "__main__":
    main()
