# -*- coding: utf-8 -*-
"""《老一辈的爱情》v2 进度 + 存活校验（人和自动化共用）。

不是简单数文件：计数器说正常、进程其实早崩了，是这轮反复吃的亏。
所以同时看四件事——计数 / 进程 / 新鲜度（最新产物距今多久）/ 一致性（状态文件标完成的镜在磁盘上是否真有）。
用法：python mv_status.py
"""
import datetime as dt
import io
import json
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = r"E:\MV-temp\laoyibei-v2"
WORK = os.path.join(ROOT, "work")
KF = os.path.join(ROOT, "laoyibei-v2fix-kv-frames")
CLIPS = os.path.join(ROOT, "laoyibei-v2fix-mv-clips")
ALL = os.path.join(ROOT, "clips-all")
STATE = os.path.join(ROOT, "state")
BANK_FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "laoyibei-v2fix_shot_bank.json")
TOTAL = len(json.load(io.open(BANK_FIX, encoding="utf-8"))["shots"])
NO_WIN = 0x08000000
issues = []


def age_min(path):
    if not path or not os.path.exists(path):
        return None
    return (dt.datetime.now() - dt.datetime.fromtimestamp(os.path.getmtime(path))).total_seconds() / 60.0


def newest(d, pattern=None):
    """返回 (最新文件路径, 符合的个数)"""
    if not os.path.isdir(d):
        return None, 0
    hits = [os.path.join(d, n) for n in os.listdir(d)
            if os.path.isfile(os.path.join(d, n)) and (not pattern or re.match(pattern, n))]
    if not hits:
        return None, 0
    return max(hits, key=os.path.getmtime), len(hits)


def procs():
    cmd = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='ffmpeg.exe'\" | "
           "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress")
    try:
        raw = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                             capture_output=True, text=True, creationflags=NO_WIN).stdout
        data = json.loads(raw) if raw.strip() else []
        if isinstance(data, dict):
            data = [data]
    except Exception:
        data = []
    out = []
    for p in data:
        c = p.get("CommandLine") or ""
        if "run_laoyibei_v2" in c:
            out.append(("driver", p.get("ProcessId")))
        elif "gen_zuindongni" in c:
            m = re.search(r"--state-tag\s+(\S+)", c)
            out.append(("生成器(%s)" % (m.group(1) if m else "?"), p.get("ProcessId")))
        elif "compose_laoyibei" in c:
            out.append(("合成", p.get("ProcessId")))
        elif "laoyibei_v2_loop" in c:
            out.append(("判定闭环", p.get("ProcessId")))
        elif "ffmpeg" in c.lower():
            out.append(("ffmpeg", p.get("ProcessId")))
    return out


def tail(path, n=40):
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8", errors="replace") as f:
        return [x.rstrip() for x in f.readlines()[-n:]]


def main():
    print("时间：%s" % dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    kf_n = sum(1 for n in os.listdir(KF) if re.match(r"kf_.*_0\.png$", n)) if os.path.isdir(KF) else 0
    clip_n = sum(1 for n in os.listdir(CLIPS) if n.startswith("shot_") and n.endswith(".mp4")
                 and not re.search(r"_\d+\.mp4$", n)) if os.path.isdir(CLIPS) else 0
    all_n = sum(1 for n in os.listdir(ALL) if n.startswith("shot_") and n.endswith(".mp4")
                and not re.search(r"_\d+\.mp4$", n)) if os.path.isdir(ALL) else 0
    print("首帧 %d/%d ｜ 重跑片段 %d/%d ｜ clips-all %d/105" % (kf_n, TOTAL, clip_n, TOTAL, all_n))

    pclip, _ = newest(CLIPS, r"shot_.*\.mp4$")
    a_clip = age_min(pclip)
    print("片段最新：%s（%s）" % (os.path.basename(pclip) if pclip else "无",
                              "%.1f 分钟前" % a_clip if a_clip is not None else "—"))

    pfrm, frm_n = newest(os.path.join(WORK, "out"), r".*\.jpg$")
    if frm_n:
        print("合成帧 %d 张 ｜ 最新 %.1f 分钟前" % (frm_n, age_min(pfrm)))

    mp4s = [os.path.join(ROOT, n) for n in os.listdir(ROOT) if n.endswith(".mp4")]
    if mp4s:
        m = max(mp4s, key=os.path.getmtime)
        print("成片：%s（%.1f MB，%.1f 分钟前）" % (os.path.basename(m),
                                              os.path.getsize(m) / 1048576.0, age_min(m)))
        # 2026-09-24 事故的盲区：改了 18 个片段，driver 的 step04 只看「旧日志里有 MV DONE
        # 且旧成片在」就宣布完成，成片其实比输入还旧，marker 却全绿。这里补上时间戳核对。
        pa, _ = newest(ALL, r"shot_.*\.mp4$")
        if pa and os.path.getmtime(pa) > os.path.getmtime(m) + 1:
            issues.append("成片比 clips-all 里的输入片段旧（%s 新于 %s，差 %.0f 分钟）"
                          "→ 这版成片不含最新片段，属「假完成」"
                          % (os.path.basename(pa), os.path.basename(m),
                             (os.path.getmtime(pa) - os.path.getmtime(m)) / 60.0))

    mk = sorted(os.listdir(STATE)) if os.path.isdir(STATE) else []
    print("marker：%s" % (", ".join(mk) if mk else "无"))
    pl = procs()
    print("进程：%s" % (", ".join("%s#%s" % t for t in pl) if pl else "（无）"))
    names = [t for t, _ in pl]
    has_gen = any(n.startswith("生成器") for n in names)
    has_driver = "driver" in names
    has_compose = "合成" in names

    if clip_n < TOTAL and not has_gen:
        issues.append("片段未齐（%d/%d）但没有生成器进程 → 已停/崩，需重启断点续跑" % (clip_n, TOTAL))
    if 0 < clip_n < TOTAL and has_gen and a_clip is not None and a_clip > 45:
        issues.append("片段停在 %d/%d、最新片段已 %.0f 分钟没动，但生成器进程还在 → 疑似卡住"
                      % (clip_n, TOTAL, a_clip))
    done_all = "DONE.ok" in mk and bool(mp4s)
    if clip_n >= TOTAL and all_n >= 105 and not has_compose and not has_driver and not done_all:
        issues.append("片段与 clips-all 都齐，但既没合成也没 driver → 流程中断")
    if has_compose and frm_n and age_min(pfrm) > 20:
        issues.append("合成进程在跑，但合成帧已 %.0f 分钟没长 → 疑似卡住" % age_min(pfrm))

    for tag in ("v2a", "v2b", "v2loop1", "v2loop2"):
        sp = os.path.join(ROOT, "laoyibei-v2fix%s-gen-state.json" % tag)
        if not os.path.exists(sp):
            continue
        try:
            st = json.load(io.open(sp, encoding="utf-8"))["shots"]
        except Exception:
            continue
        done = [k for k, v in st.items() if isinstance(v, dict) and v.get("status") == "completed"]
        miss = [k for k in done if not os.path.exists(os.path.join(CLIPS, "shot_%s.mp4" % k))]
        if miss:
            issues.append("state(%s) 标完成、磁盘上却没有片段：%s" % (tag, " ".join(miss[:8])))

    for name in ("driver_v2.out.log", "driver_v2.err.log", "loop.out.log", "loop.err.log"):
        for ln in tail(os.path.join(ROOT, name)):
            if re.search(r"(Traceback|Error|FAILED|失败|HTTP 5\d\d)", ln):
                issues.append("%s 有异常行：%s" % (name, ln[:140]))
                break

    if issues:
        print("\n判定：发现 %d 处不对 ——" % len(issues))
        for i in issues:
            print("  · " + i)
    elif done_all and not pl:
        print("\n判定：已完成（DONE.ok + 成片都在，当前没有进程在跑——这是正常收尾状态）")
    else:
        print("\n判定：正常（计数、进程、新鲜度、一致性都对得上）")


if __name__ == "__main__":
    main()
