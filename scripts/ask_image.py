# -*- coding: utf-8 -*-
"""把一张本地图片交给视觉模型（默认 agnes-3.0-flash）描述/定向追问。

用法：python ask_image.py <图片路径> ["问题"]
环境变量：AGNES_API_KEY（必填）、AGNES_BASE_URL、MV_VISION_MODEL（默认 agnes-3.0-flash）

纪律（踩过的坑）：**只喂单张全尺寸**。缩略图/拼图会让视觉模型幻觉出并不存在的
文字与人数；几何二次加工图（裁切/拼图/缩放）不能作为定性依据。
"""
import base64, io, json, os, re, sys, time, urllib.request
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # 结论里是中文，避免控制台编码把字弄乱
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _mvcfg import BASE_URL, api_key, get  # noqa: E402

KEY = api_key()
MODEL = get("MV_VISION_MODEL", "agnes-3.0-flash")

path = sys.argv[1]
question = sys.argv[2] if len(sys.argv) > 2 else "Describe this image in detail."

im = Image.open(path).convert("RGB")
w, h = im.size
print("size %dx%d" % (w, h), flush=True)
im = im.resize((720, int(720 * h / w)), Image.LANCZOS)
b = io.BytesIO(); im.save(b, "JPEG", quality=85)

body = {"model": MODEL, "max_tokens": 1200, "messages": [{"role": "user", "content": [
    {"type": "text", "text": question},
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()}}]}]}

for a in range(4):
    try:
        rq = urllib.request.Request(BASE_URL + "/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
        d = json.loads(urllib.request.urlopen(rq, timeout=180).read().decode())
        m = d["choices"][0]["message"]
        print((m.get("content") or m.get("reasoning_content") or "").strip())
        break
    except Exception as e:
        print("retry %s" % e, flush=True)
        time.sleep(6 + a * 6)
