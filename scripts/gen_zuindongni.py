# -*- coding: utf-8 -*-
"""按分镜库批量生成「首帧 → 第二关键帧（i2i 派生）→ i2v 视频候选」的生成器。

三个关键机制（都是踩过坑换来的，别改掉）：

1. **先出首帧过闸门，再进视频**：`--kf-only` 只出关键帧；首帧没过人工/视觉闸门前
   不要开跑视频（方向、人数、景别都在这一步定型，文字纠不回来）。
2. **第二关键帧从首帧 i2i 派生**，不要两张独立生成——独立生成会让模型在两张之间插值，
   出现双头/鬼影。派生提示词要单独写"推进到哪里"（`kf1_prompt` 字段），
   并且要与首帧**同人数、同结构**。
3. **断点续跑**：每个镜的进度写进 state JSON，崩溃/断网后重跑自动跳过已完成的。
   多路并行用 `--t0-min/--t0-max/--state-tag`，每路一个独立 state 文件。

⚠️ 出图读的是 `shot["keyframes"][i]`，**不是** `shot["keyframe_prompt"]`——
改提示词要改模型真正读到的那一份（改完回读断言）。

环境变量：AGNES_API_KEY（必填）、AGNES_BASE_URL、
  MV_KF_MODEL（首帧图像模型，默认 agnes-image-2.1-flash）、
  MV_I2I_MODEL（派生帧模型，默认同上）、
  MV_I2V_MODEL（视频模型，默认 agnes-video-v2.0）、
  ZDN_CAND（覆盖每镜候选数上限）、FFMPEG_BIN / FFPROBE_BIN / CURL_BIN、
  MV_UPLOAD_URL / MV_UPLOAD_FIELD（垫图图床；默认 https://uguu.se/upload，字段 files[]）、
  MV_UPLOAD_DISABLE（=1 时禁止上传，离线自检用）

⚠️ **垫图会上传到图床**：默认是一家匿名公共图床，含人脸的关键帧会变成公开可访问的 URL；
   要换成自建/私有图床请设 `MV_UPLOAD_URL`（需兼容 `curl -F <字段>=@文件 <URL>`）。
   上传后会再用 HTTP Range 探活（图床偶发 404 会让生成任务拿到坏链接、静默失败，见 references/pipeline.md §4）。

用法：python gen_zuindongni.py --bank <分镜库.json> --outdir <中间产物目录> [--kf-only] [--only A1-3]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _mvcfg import (BASE_URL, CURL, FFMPEG, FFPROBE, MV_WORK, NO_WIN,  # noqa: E402
                    NULL_DEVICE, get)

KEY = get("AGNES_API_KEY", "")     # 密钥只走环境变量/.env，禁止写进仓库
BASE = BASE_URL
POLL_SEC = 15
KF_MODEL = get("MV_KF_MODEL", "agnes-image-2.1-flash")
I2I_MODEL = get("MV_I2I_MODEL", "agnes-image-2.1-flash")
I2V_MODEL = get("MV_I2V_MODEL", "agnes-video-v2.0")
LOCK = threading.Lock()
# NO_WIN（子进程静默，避免 Windows 上闪控制台窗口）来自 _mvcfg：非 Windows 平台它必须是 0，
# 否则 subprocess 直接抛 ValueError（v3.1 修的跨平台 bug，见 _mvcfg 文件头与 SKILL §5 #42）。
UPLOAD_URL = get("MV_UPLOAD_URL", "https://uguu.se/upload")
UPLOAD_FIELD = get("MV_UPLOAD_FIELD", "files[]")
UPLOAD_DISABLED = get("MV_UPLOAD_DISABLE") == "1"
_upload_notice_shown = False

STYLE = ("写实电影摄影：35mm 胶片质感，浅景深，真实自然的皮肤与织物纹理，电影级布光，"
         "细腻的暗部层次与轻微颗粒感，纪实、克制，无文字无水印")

# 2026-09-25：风格可被分镜库覆盖（《两岸统一》是国风动漫，不能再挂写实尾巴）。
# 库里有 _meta.style_prompt / _meta.kf1_style 时优先用它；没有时行为与从前完全一致。
KF1_STYLE = "写实电影摄影，真实皮肤与织物质感，浅景深，无文字无水印"

# ⚠️ 下面是**仓库自带的示例角色卡**（作者早期项目的历史默认值，脱敏但仍带具体设定）。
# 真项目请在分镜库里用 _meta.ids 覆盖，或写 "ids": {} 跳过定妆照阶段；
# 两者都没有时会在开工时打印警告，避免"以为在跑自己的歌、其实在用示例角色卡"。
IDS = {
    "妈妈": ("28-33岁的中国年轻母亲，齐肩黑发低马尾，面庞清秀；服装从头到尾不变："
             "米白色旧棉衣、枣红色旧围裙（胸前一个小口袋）、深蓝碎花背带把熟睡的婴儿背在身后；"
             "站在清晨早点摊前，半身中景，正面偏侧。清晨冷青光。"),
    "哥哥": ("6-8岁的中国小男孩，瘦小但精神，短发，眼神干净懂事；服装从头到尾不变："
             "藏蓝色旧棉袄（袖口磨白）、深灰棉裤、蓝白相间旧运动鞋；"
             "蹲在早点摊边的小凳旁摘菜，中景。清晨冷青光。"),
    "大哥": ("40岁左右的中国中年男子，普通劳动者，短发，面容朴实；服装从头到尾不变："
             "深灰色旧夹克、黑色长裤、黑色运动鞋；站在清晨街头，中景。晨光金色。"),
    "老人": ("70多岁的中国老人，灰白头发稀疏，背明显佝偻，面容沧桑但有尊严；服装从头到尾不变："
             "洗得发灰的旧外套、深灰旧棉裤、旧布鞋；怀里护着湿透的旧衣包袱，"
             "缩在雨夜街边雨檐下躲雨，中景。雨夜冷蓝路灯。"),
    "少年": ("16-18岁的中国少年，学生模样，短发清秀；服装从头到尾不变："
             "深蓝色卫衣、牛仔裤、白色运动鞋、深色书包；撑伞站在雨夜街头，中景。雨夜冷蓝路灯。"),
}


def api_get(path, key):
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_post(path, body, key, timeout=240):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode("utf-8"),
                                 headers={"Authorization": "Bearer " + key,
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_retry(path, body, key, label, attempts=8, wait0=18):
    for attempt in range(attempts):
        try:
            return api_post(path, body, key)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                wait = min(wait0 * (attempt + 1), 90)
                print(f"{label} HTTP {e.code}, wait {wait}s", flush=True)
                time.sleep(wait)
            else:
                print(f"{label} HTTP {e.code}", flush=True)
                time.sleep(15)
        except Exception as e:
            print(f"{label} err: {e}", flush=True)
            time.sleep(15)
    return None


def upload(path):
    """把垫图传到图床，返回可公开访问的 URL。

    为什么要图床：i2v/i2i 接口只吃 URL，不吃本地文件。
    ⚠️ 默认图床是**匿名公共**的：含人脸的关键帧会变成公开可访问的 URL。介意就设 MV_UPLOAD_URL。
    """
    global _upload_notice_shown
    if UPLOAD_DISABLED:
        sys.exit("MV_UPLOAD_DISABLE=1：本轮禁止上传垫图（离线自检模式）。"
                 "要走真接口请取消该变量，或把 MV_UPLOAD_URL 指向你自己的图床。")
    if not _upload_notice_shown:
        _upload_notice_shown = True
        print(f"垫图图床：{UPLOAD_URL}（匿名公共图床；换自建图床设 MV_UPLOAD_URL）", flush=True)
    for _ in range(3):
        try:
            raw = subprocess.run(
                [CURL, "-s", "--max-time", "90", "-F",
                 f"{UPLOAD_FIELD}=@{path}", UPLOAD_URL],
                capture_output=True, text=True, creationflags=NO_WIN).stdout
            url = json.loads(raw)["files"][0]["url"]
            r = subprocess.run([CURL, "-s", "-o", NULL_DEVICE, "-w", "%{http_code}",
                                "--max-time", "30", "-r", "0-0", url],
                               capture_output=True, text=True,
                               creationflags=NO_WIN).stdout.strip()
            if r in ("200", "206"):
                return url
        except Exception as e:
            print(f"upload err: {e}", flush=True)
        time.sleep(8)
    return None


def download(url, out, attempts=4):
    for _ in range(attempts):
        subprocess.run([CURL, "-s", "-L", "--max-time", "240", "-o", out, url],
                       check=False, creationflags=NO_WIN)
        if os.path.exists(out) and os.path.getsize(out) > 10000:
            return True
        time.sleep(10)
    return False


def valid_clip(path):
    if not os.path.exists(path) or os.path.getsize(path) < 10000:
        return False
    r = subprocess.run([FFPROBE, "-v", "error",
                        "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True, creationflags=NO_WIN)
    return r.returncode == 0 and bool(r.stdout.strip())


def crop_916(img_path, out_path):
    # 用 with 关掉文件句柄：否则图片损坏抛异常时会锁住文件，后面连删都删不掉
    with Image.open(img_path) as im:
        img = im.convert("RGB")
    w, h = img.size
    target = 9 / 16
    if w / h > target:
        nw = int(h * target)
        x = (w - nw) // 2
        img = img.crop((x, 0, x + nw, h))
    else:
        nh = int(w / target)
        y = (h - nh) // 2
        img = img.crop((0, y, w, y + nh))
    img = img.resize((768, 1344), Image.LANCZOS)
    img.save(out_path)


def extract_tail(clip, out_png):
    subprocess.run([FFMPEG, "-y", "-v", "error", "-sseof", "-0.2", "-i", clip,
                    "-frames:v", "1", out_png], check=False, creationflags=NO_WIN)
    return os.path.exists(out_png) and os.path.getsize(out_png) > 5000


def poll_one(tid, key, idx, clip_dir, nf):
    try:
        st = api_get(f"/agnesapi?video_id={tid}", KEY)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            nf[tid] = nf.get(tid, 0) + 1
            if nf[tid] < 6:
                return False
        print(f"{key} TASK HTTP {e.code}", flush=True)
        return "failed"
    except Exception:
        return False
    if st.get("status") == "completed" and st.get("url"):
        cand = os.path.join(clip_dir, f"shot_{key}_{idx}.mp4")
        if download(st["url"], cand) and valid_clip(cand):
            final = os.path.join(clip_dir, f"shot_{key}.mp4")
            if not valid_clip(final):
                shutil.copyfile(cand, final)
            print(f"{key} DONE candidate{idx}", flush=True)
            return True
        if os.path.exists(cand):
            os.remove(cand)
    elif st.get("status") == "failed":
        return "failed"
    elif st.get("error") not in (None, {}, "", False):
        return "failed"
    return False


def gen_image(prompt, label):
    # 竖版 9:16：必须显式传 size，否则默认方形，两侧构图会被裁掉
    # 默认 2.1；某些细节（例如老人脸上的眼泪）2.1 画不出来时，可用环境变量换更贵的模型再试
    # KF_MODEL 是历史别名（等价于 MV_KF_MODEL）；MV_KF_MODEL 已在模块加载时读好
    body = {"model": get("KF_MODEL", KF_MODEL),
            "prompt": prompt, "size": "768x1344"}
    r = post_retry("/v1/images/generations", body, KEY, label, attempts=4, wait0=15)
    if not r:
        return None
    return (r.get("data") or [{}])[0].get("url")


def derive_kf1(p0_local, shot, out_png):
    """从首帧经 i2i 派生第二关键帧：同一人物、同一构图，只向前推进一点。
    两张独立生成的关键帧会让视频模型在两者之间插值出"双头/鬼影"，派生帧可根除。"""
    u0 = upload(p0_local)
    if not u0:
        return False
    # 2026-09-24 修的坑：原来取 i2v_prompt 的第一句当「推进」描述，而第一句是相机描述
    # （"The camera holds a static shot"／"The camera pans with small amplitude…"），
    # 人物与方向信息全被丢掉 → i2i 在没人没方向的情况下「推进」，实测会把人物整段丢掉
    # （《老一辈的爱情》P3、A4-5 的派生帧变成 0 人，A2-1、A2-2 的派生帧只剩 1 人）。
    # 视频模型在「两人一车」首帧与「一个人」派生帧之间插值，就出现自行车分身、后座奶奶腿没了；
    # 在「两人院子」首帧与「空院子」派生帧之间插值，篮子就悬空飘落；A4-5 则变成倒退走。
    # 现在优先吃分镜库里专门的「推进·方向」字段 kf1_prompt。
    move = shot.get("kf1_prompt") or (shot.get("i2v_prompt") or "").split("。")[0]
    cam_lock = ("【机位锁】机位、景别、视角与画面大小完全不变：不要推拉镜头、不要变焦、"
                "不要把镜头拉远或拉近、不要抬高或降低机位、不要改变透视与背景比例；")
    # 2026-09-25《两岸统一》小样实测：无人镜沿用「人物一个都不能少」的锁时，提示词本身反复提到
    # 人物/人数/长相，i2i 就会在空场景里凭空画一个人（试跑 3/3 命中）。所以按镜型换锁，
    # 由分镜库的 kf1_lock_mode 决定（none/hands/sil/people，缺省 people＝旧行为）。
    mode = shot.get("kf1_lock_mode") or "people"
    if mode == "none":
        head = "保持同一处场景、同一机位与同一种色调；"
        body = ("【无人锁】画面里从头到尾没有任何人物，人数恒为 0：不要新增人、人影、剪影或远处的小人，"
                "不要改变景物、建筑、物件的位置与数量，不要改变画幅比例。")
    elif mode == "hands":
        head = "保持同一双手、同一处场景与同一种色调；"
        body = ("【手部锁】画面里始终只有那双手与袖口：不要出现脸、头、上半身或任何第二个人，"
                "画面上下左右四边也不出现下巴、嘴唇、脖颈、头发与肩膀，"
                "不要多出手指或改变握持关系，不要改变画幅比例。")
    elif mode == "sil":
        head = "保持同一处场景、同一机位与同一种色调；"
        body = ("【剪影锁】画面里始终只有两个小剪影：不要多出第三个人，也不要少一个人，"
                "不要让他们变成清晰五官，不要改变两个剪影的相对位置，不要改变画幅比例。")
    elif mode == "crowd":
        # 人文镜（庙会绕境／夜市／茶园／丰年祭／渡轮人流）：有远景人影是对的，
        # 锁的是"不成形"而不是"没有人"——一旦写"不能有人"，i2i 会把这些镜的人影整段抹掉。
        head = "保持同一处场景、同一机位与同一种色调；"
        body = ("【人群锁】画面里仍然是那群远景人影或剪影，人数与位置的疏密关系保持原样："
                "不要把人影抹掉、也不要新增，不要让任何一个人变成清晰五官或正脸，不要改变画幅比例。")
    else:
        head = "保持同一个人物、同一处场景与同一种色调；"
        body = ("画面里的人一个都不能少、一个都不能多：不要新增人物，也不要让人物离开画面或消失在画外，"
                "不要改变人物的长相、服装、人数与人物之间的位置关系，不要改变画幅比例。")
    prompt = (head + cam_lock + body + "画面只沿原来的方向前进一点点：%s。%s") % (move, KF1_STYLE)
    body = {"model": I2I_MODEL, "prompt": prompt, "size": "768x1344",
            "extra_body": {"image": [u0]}}
    r = post_retry("/v1/images/generations", body, KEY, "i2i", attempts=4, wait0=15)
    url = (r.get("data") or [{}])[0].get("url") if r else None
    if not url:
        return False
    raw = out_png[:-4] + "_raw.png"
    if not download(url, raw, attempts=3):
        return False
    Image.open(raw).convert("RGB").resize((768, 1344), Image.LANCZOS).save(out_png)
    return os.path.exists(out_png) and os.path.getsize(out_png) > 5000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", required=True)
    ap.add_argument("--outdir", default=os.path.join(MV_WORK, "mv-project"),
                    help="中间产物目录（关键帧/片段/state/日志都落这里）")
    ap.add_argument("--api-key", default=KEY)
    ap.add_argument("--kf-only", action="store_true",
                    help="只生成关键帧，不进视频阶段（先人工/视觉质检首帧再决定是否开跑）")
    ap.add_argument("--t0-min", type=float, default=0.0,
                    help="只处理 t0 大于等于该秒数的镜（用于把全曲拆成几段并行跑）")
    ap.add_argument("--t0-max", type=float, default=0.0,
                    help="只处理 t0 小于该秒数的镜（0 表示不限）")
    ap.add_argument("--state-tag", default="",
                    help="给这一路进程单独的 state 文件名后缀，多段并行时避免互相覆盖")
    ap.add_argument("--only", default="",
                    help="只跑点名的那几个镜（逗号分隔），供自动返修循环单镜重出用")
    args = ap.parse_args()

    bank = json.load(open(args.bank, encoding="utf-8"))
    # v2 bank 自带 ids（_meta.ids）与更细的锚点（妈妈胸前/背后/围巾/回忆组合等）
    bank_meta = bank.get("_meta", {})
    # 2026-09-25：风格尾巴由分镜库注入（国风动漫 / 沙画 / 写实各不相同）
    global STYLE, KF1_STYLE
    if bank_meta.get("style_prompt"):
        STYLE = bank_meta["style_prompt"]
    if bank_meta.get("kf1_style"):
        KF1_STYLE = bank_meta["kf1_style"]
    bank_ids = bank_meta.get("ids")
    # v3：ids 显式为空 dict 时跳过定妆照阶段（第二关键帧已改由 i2i 派生，不再需要定妆照垫图）
    if bank_ids is not None:
        IDS.clear()
        IDS.update(bank_ids)
    elif IDS:
        print("警告：分镜库没有 _meta.ids，本轮将使用**脚本内置的示例角色卡**（%s）——"
              "那是仓库示例、不是你的角色。请在分镜库 _meta.ids 里给全，"
              '或显式写 "ids": {} 跳过定妆照阶段。' % "、".join(IDS), flush=True)
    bank_name = os.path.splitext(os.path.basename(args.bank))[0]
    if bank_name.endswith("_shot_bank"):
        bank_name = bank_name[: -len("_shot_bank")]
    shots = bank["shots"]
    if args.t0_min:
        shots = [s for s in shots if s["t0"] >= args.t0_min - 0.001]
        print("filtered to %d shots from t0 >= %.2fs" % (len(shots), args.t0_min), flush=True)
    if args.t0_max:
        shots = [s for s in shots if s["t0"] < args.t0_max - 0.001]
        print("filtered to %d shots from t0 < %.2fs" % (len(shots), args.t0_max), flush=True)
    if args.only:
        want = {k.strip() for k in args.only.split(",") if k.strip()}
        shots = [s for s in shots if s["key"] in want]
        print("filtered to %d shots by --only" % len(shots), flush=True)
    negative = bank["negative_prompt"]
    kf_dir = os.path.join(args.outdir, f"{bank_name}-kv-frames")
    clip_dir = os.path.join(args.outdir, f"{bank_name}-mv-clips")
    meta_path = os.path.join(args.outdir, f"{bank_name}_clip_meta.json")
    state_path = os.path.join(args.outdir,
                              f"{bank_name}{args.state_tag}-gen-state.json")
    os.makedirs(kf_dir, exist_ok=True)
    os.makedirs(clip_dir, exist_ok=True)
    state = json.load(open(state_path, encoding="utf-8")) if os.path.exists(state_path) else {"ids": {}, "kf": {}, "shots": {}}
    meta = json.load(open(meta_path, encoding="utf-8")) if os.path.exists(meta_path) else {}

    # ---- Phase 0: 定妆照（每角色 2 候选，取第 0 张作锚点）----
    for name, prompt in IDS.items():
        done = state["ids"].get(name, [])
        if len(done) >= 2:
            print(f"id {name} exists", flush=True)
            continue
        for i in range(len(done), 2):
            out_png = os.path.join(kf_dir, f"id_{name}_{i}.png")
            raw_png = os.path.join(kf_dir, f"raw_id_{name}_{i}.png")
            if os.path.exists(out_png) and os.path.getsize(out_png) > 5000:
                done.append(out_png)
                state["ids"][name] = done
                json.dump(state, open(state_path, "w", encoding="utf-8"))
                continue
            url = gen_image(f"{prompt}。{STYLE}", f"id {name} {i}")
            if not url or not download(url, raw_png, attempts=3):
                print(f"id {name} {i} FAILED", flush=True)
                sys.exit(1)
            crop_916(raw_png, out_png)
            done.append(out_png)
            state["ids"][name] = done
            json.dump(state, open(state_path, "w", encoding="utf-8"))
            print(f"id {name} {i} OK", flush=True)
            time.sleep(3)

    # ---- Phase 1: 每镜动作关键帧（3 并发；文件存在即断点）----
    tasks = []
    for s in shots:
        key = s["key"]
        for i, kp in enumerate(s.get("keyframes") or []):
            out_png = os.path.join(kf_dir, f"kf_{key}_{i}.png")
            if not (os.path.exists(out_png) and os.path.getsize(out_png) > 5000):
                tasks.append((key, i, kp, out_png))
    print(f"Phase1 keyframes to generate: {len(tasks)}", flush=True)

    def _make_kf(t):
        key, i, kp, out_png = t
        raw_png = os.path.join(kf_dir, f"raw_kf_{key}_{i}.png")
        try:
            url = gen_image(kp, f"{key} kf{i}")
            if not url or not download(url, raw_png, attempts=3):
                print(f"{key} kf{i} FAILED", flush=True)
                return False
            crop_916(raw_png, out_png)
        except Exception as e:
            # 下载被截断（image file is truncated）这类单张故障不能让整批崩掉：
            # 删掉残图后返回 False，由上层按断点续跑重出这一张。
            print(f"{key} kf{i} ERR {type(e).__name__}: {e}", flush=True)
            for p in (raw_png, out_png):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except OSError as e2:
                    print(f"{key} kf{i} 残图删不掉（留着，下次会重下）: {e2}", flush=True)
            return False
        print(f"{key} kf{i} OK", flush=True)
        return True

    if tasks:
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(_make_kf, tasks))
        if not all(results):
            print("Phase1 FAILED, exit for supervisor retry", flush=True)
            sys.exit(1)
    # 从磁盘重建 kf 列表（文件是唯一事实源，线程安全）
    for s in shots:
        key = s["key"]
        frames = []
        for i, _kp in enumerate(s.get("keyframes") or []):
            p = os.path.join(kf_dir, f"kf_{key}_{i}.png")
            if os.path.exists(p) and os.path.getsize(p) > 5000:
                frames.append(p)
        if len(frames) == len(s.get("keyframes") or []):
            state["kf"][key] = frames
    json.dump(state, open(state_path, "w", encoding="utf-8"))

    if args.kf_only:
        # 2026-09-24：首帧闸门要连**派生第二关键帧**一起过。验证过《老一辈的爱情》v5 的
        # 四条新问题（篮子飘落／自行车分身／后座奶奶腿没了／老人倒退）根因全在派生帧：
        # 旧的 derive_kf1 吃的是 i2v 第一句相机描述，i2i 在没有人没有方向的情况下「推进」，
        # 把人物整段丢了。所以 --kf-only 也把 kf1x 派生出来，让闸门一次把两张关键帧都看完。
        for s in shots:
            key = s["key"]
            if s.get("chain_prev"):
                continue
            kf1x = os.path.join(kf_dir, f"kf1x_{key}.png")
            if os.path.exists(kf1x) and os.path.getsize(kf1x) > 5000:
                print(f"{key} kf1 exists", flush=True)
                continue
            if not derive_kf1(state["kf"][key][0], s, kf1x):
                print(f"{key} derive kf1 failed", flush=True)
                sys.exit(1)
            print(f"{key} kf1 derived", flush=True)
        print("KF-ONLY DONE, keyframes in", kf_dir, flush=True)
        return

    # ---- Phase 2: 视频（镜头串行=链依赖；候选并行）----
    key2shot = {s["key"]: s for s in shots}
    sorted_shots = sorted(shots, key=lambda x: x["t0"])
    next_t0 = {}
    for i, s in enumerate(sorted_shots):
        nxt = sorted_shots[i + 1]["t0"] if i + 1 < len(sorted_shots) else s["t1"]
        next_t0[s["key"]] = nxt

    for s in shots:
        key = s["key"]
        # 2026-09-25《两岸统一》：免费额度 429 风暴时，每镜 2–3 条候选会把并发推高、
        # 等待时间指数增长（实测 18→90s）。用 ZDN_CAND 限制本路提交条数（不改分镜库），
        # 先拿一版完整成片，个别镜不满意再用 --only 单镜重出。
        cand_n = max(1, min(int(s.get("candidates", 2)),
                            int(os.environ.get("ZDN_CAND", "9"))))
        st = state["shots"].get(key, {})
        final = os.path.join(clip_dir, f"shot_{key}.mp4")
        final_ok = valid_clip(final)
        if final_ok and st.get("done"):
            print(f"{key} already done, skip", flush=True)
            continue
        if os.path.exists(final) and not st.get("done"):
            os.remove(final)

        # 组装垫图（v3）：链式=[上一镜尾帧, 本镜首帧]；其余=[首帧, i2i 派生帧]
        chain_prev = s.get("chain_prev")
        frames = state["kf"][key]
        urls = []
        if chain_prev and chain_prev in key2shot:
            prev_final = os.path.join(clip_dir, f"shot_{chain_prev}.mp4")
            if not valid_clip(prev_final):
                print(f"{key} waiting prev {chain_prev}", flush=True)
                sys.exit(1)
            tail_png = os.path.join(kf_dir, f"tail_{chain_prev}.png")
            if not os.path.exists(tail_png):
                extract_tail(prev_final, tail_png)
            imgs_local = [tail_png, frames[0]]
        else:
            kf1x = os.path.join(kf_dir, f"kf1x_{key}.png")
            if not (os.path.exists(kf1x) and os.path.getsize(kf1x) > 5000):
                if not derive_kf1(frames[0], s, kf1x):
                    print(f"{key} derive kf1 failed", flush=True)
                    sys.exit(1)
                print(f"{key} kf1 derived", flush=True)
            imgs_local = [frames[0], kf1x]
        for p in imgs_local:
            u = upload(p)
            if not u:
                sys.exit(1)
            urls.append(u)
            time.sleep(2)
        print(f"{key} keyframes: {len(urls)}", flush=True)

        # 单个镜自己的时长优先（子集 bank 重跑时，next_t0 会跨到很远的下一镜）
        seg_end = s.get("t1") or next_t0[s["key"]]
        seg_need = (seg_end - s["t0"]) + 0.5
        raw_frames = max(121, int(seg_need * 24))
        num_frames = min(249, ((raw_frames - 1 + 7) // 8) * 8 + 1)
        neg = negative + (s.get("negative_extra") or "")
        body = {"model": I2V_MODEL, "prompt": s["i2v_prompt"],
                "width": 768, "height": 1344, "num_frames": num_frames,
                "frame_rate": 24, "negative_prompt": neg,
                "extra_body": {"mode": "keyframes", "image": urls[:3]}}

        ids = st.get("task_ids", [])
        pending = {i: tid for i, tid in enumerate(ids)}
        submit_attempts = {i: 1 for i in pending}
        results = {}
        with ThreadPoolExecutor(max_workers=3) as pool:
            futs = {}
            for i in range(cand_n):
                if i in pending:
                    continue
                def _sub(slot=i, _body=body):
                    r = post_retry("/v1/videos", _body, KEY, f"{key} i2v{slot}")
                    if r and (r.get("video_id") or r.get("task_id")):
                        results[slot] = ("ok", r.get("video_id") or r.get("task_id"))
                    else:
                        results[slot] = ("fail", None)
                futs[pool.submit(_sub)] = i
            for fut in futs:
                fut.result()
        for i in range(cand_n):
            if i not in pending and i in results and results[i][1]:
                pending[i] = results[i][1]
        st["task_ids"] = [pending[i] for i in sorted(pending)]
        state["shots"][key] = st
        json.dump(state, open(state_path, "w", encoding="utf-8"))

        nf = {}
        while pending:
            for i in list(pending):
                tid = pending[i]
                r = poll_one(tid, key, i, clip_dir, nf)
                if r is True:
                    del pending[i]
                    break
                if r == "failed":
                    del pending[i]
                    if submit_attempts.get(i, 0) < 2:
                        submit_attempts[i] = submit_attempts.get(i, 0) + 1
                        r2 = post_retry("/v1/videos", body, KEY, f"{key} i2v{i} retry")
                        if r2 and (r2.get("video_id") or r2.get("task_id")):
                            pending[i] = r2.get("video_id") or r2.get("task_id")
                    break
            if pending:
                time.sleep(POLL_SEC)
        if not valid_clip(final):
            print(f"{key} NO final", flush=True)
            sys.exit(1)
        st["done"] = True
        state["shots"][key] = st
        json.dump(state, open(state_path, "w", encoding="utf-8"))
        meta[key] = {"key": key, "file": f"{bank_name}-mv-clips/shot_{key}.mp4",
                     "lyric": s["lyric"], "time": s["time"], "style": s["style"],
                     "seconds": s["seconds"], "chain_prev": chain_prev}
        json.dump(meta, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"{key} video done", flush=True)

    print("gen_shanyi_anime DONE ->", meta_path)


if __name__ == "__main__":
    main()
