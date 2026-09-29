# -*- coding: utf-8 -*-
"""通用：把一张本地图片交给 agnes-3.0-flash 描述。用法：ask_image.py <图片路径> ["问题"]"""
import base64, io, json, os, re, sys, time, urllib.request
from PIL import Image

WORK = r"C:\Users\Huangzelong\Documents\Codex\2026-09-09\ni\work"
KEY = os.environ.get("AGNES_API_KEY") or ""   # 发布版：密钥只走环境变量，禁止写进仓库

path = sys.argv[1]
question = sys.argv[2] if len(sys.argv) > 2 else "Describe this image in detail."

im = Image.open(path).convert("RGB")
w, h = im.size
print("size %dx%d" % (w, h), flush=True)
im = im.resize((720, int(720 * h / w)), Image.LANCZOS)
b = io.BytesIO(); im.save(b, "JPEG", quality=85)

body = {"model": "agnes-3.0-flash", "max_tokens": 1200, "messages": [{"role": "user", "content": [
    {"type": "text", "text": question},
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()}}]}]}

for a in range(4):
    try:
        rq = urllib.request.Request("https://apihub.agnes-ai.cn/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
        d = json.loads(urllib.request.urlopen(rq, timeout=180).read().decode())
        m = d["choices"][0]["message"]
        print((m.get("content") or m.get("reasoning_content") or "").strip())
        break
    except Exception as e:
        print("retry %s" % e, flush=True)
        time.sleep(6 + a * 6)
