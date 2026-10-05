# -*- coding: utf-8 -*-
"""进度与存活自检：**计数 / 进程 / 新鲜度 / 一致性**四件事一起看。

为什么不能只数文件——两件反复吃过的事：

1. **计数器说正常、进程其实早崩了**：片段数停在半路，但没人发现生成器已经退出。
2. **"假完成"**：驱动脚本只看"旧日志里有 `MV DONE`、旧成片还在"就宣布完成，
   而成片其实比输入片段还旧——marker 全绿，成片里却没有新片段。

守夜/自动化每一轮的第一步都应该是它，而不是凭感觉说"还在跑"。

用法：
    set MV_PROJECT=<项目中间产物根目录>
    python status.py

环境变量：
    MV_PROJECT  项目目录（必填）：约定里面有 work/、state/、clips-all/、
                以及形如 <名字>-kv-frames / <名字>-mv-clips 的目录
    MV_BANK     分镜库 JSON；不给则在 MV_PROJECT 里自动找 *_shot_bank.json

退出码：0 = 正常；1 = 发现异常（可直接当守夜或 CI 的门槛）
"""
import datetime as dt
import glob
import io
import json
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _mvcfg import NO_WIN  # noqa: E402

issues = []

ROOT = os.environ.get("MV_PROJECT")
if not ROOT or not os.path.isdir(ROOT):
    sys.exit("请设 MV_PROJECT 指向项目中间产物根目录（当前：%r）" % ROOT)
WORK = os.path.join(ROOT, "work")
STATE = os.path.join(ROOT, "state")
ALL = os.path.join(ROOT, "clips-all")


def _first_dir(suffix):
    hits = sorted(glob.glob(os.path.join(ROOT, "*" + suffix)))
    return hits[0] if hits else os.path.join(ROOT, suffix.strip("-"))


KF = _first_dir("-kv-frames")
CLIPS = _first_dir("-mv-clips")

BANK = os.environ.get("MV_BANK")
if not BANK:
    cand = sorted(glob.glob(os.path.join(ROOT, "*.json")) +
                  glob.glob(os.path.join(ROOT, "work", "*_shot_bank.json")))
    BANK = next((c for c in cand if c.endswith("_shot_bank.json")), None)
TOTAL = 0
if BANK and os.path.isfile(BANK):
    try:
        TOTAL = len(json.load(io.open(BANK, encoding="utf-8"))["shots"])
    except Exception as e:
        issues.append("读分镜库失败（%s）：%s" % (os.path.basename(BANK), e))


def age_min(path):
    if not path or not os.path.exists(path):
        return None
    return (dt.datetime.now() - dt.datetime.fromtimestamp(os.path.getmtime(path))).total_seconds() / 60.0


def newest(d, pattern=None):
    """返回 (最新文件路径, 符合的个数)。"""
    if not os.path.isdir(d):
        return None, 0
    hits = [os.path.join(d, n) for n in os.listdir(d)
            if os.path.isfile(os.path.join(d, n)) and (not pattern or re.match(pattern, n))]
    return (max(hits, key=os.path.getmtime), len(hits)) if hits else (None, 0)


def count_shots(d):
    """数片段：排除 shot_x_1.mp4 这类候选文件。"""
    if not os.path.isdir(d):
        return 0
    return sum(1 for n in os.listdir(d) if n.startswith("shot_") and n.endswith(".mp4")
               and not re.search(r"_\d+\.mp4$", n))


# 进程关键词 → 显示名。按自己的驱动脚本名加一行即可。
PROC_KEYWORDS = (("生成器", "gen_zuindongni"), ("合成", "compose_"),
                 ("驱动", "run_"), ("判定闭环", "_loop"), ("ffmpeg", "ffmpeg"))


def procs():
    """返回 [(标签, pid)]；**取不到进程列表时返回 None**（不要静默当成"没有进程在跑"——
    那正好会伪造出"生成器已崩"或"一切正常"的假结论，而这两个结论正是本脚本要防的）。"""
    if os.name == "nt":
        # portability-scan-allow: 这一段只在 os.name == "nt" 分支里执行
        cmd = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='ffmpeg.exe'\" | "
               "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress")
        argv = ["powershell", "-NoProfile", "-Command", cmd]  # portability-scan-allow: 仅 Windows 分支
    else:
        argv = ["ps", "-eo", "pid,args"]
    try:
        raw = subprocess.run(argv, capture_output=True, text=True,
                             creationflags=NO_WIN).stdout
        data = json.loads(raw) if raw.strip().startswith(("{", "[")) else raw
        if isinstance(data, dict):
            data = [data]
    except Exception:
        return None
    out = []
    if isinstance(data, list) and data and isinstance(data[0], dict):
        for p in data:
            c = p.get("CommandLine") or ""
            for label, kw in PROC_KEYWORDS:
                if kw in c:
                    out.append((label, p.get("ProcessId")))
                    break
    else:
        for line in str(data).splitlines():
            for label, kw in PROC_KEYWORDS:
                if kw in line:
                    m = re.match(r"\s*(\d+)", line)
                    out.append((label, m.group(1) if m else "?"))
                    break
    return out


def tail(path, n=40):
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8", errors="replace") as f:
        return [x.rstrip() for x in f.readlines()[-n:]]


def main():
    print("时间：%s" % dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    kf_n = sum(1 for n in os.listdir(KF) if re.match(r"kf_.*_0\.png$", n)) if os.path.isdir(KF) else 0
    clip_n, all_n = count_shots(CLIPS), count_shots(ALL)
    print("首帧 %d/%d ｜ 区域片段 %d/%d ｜ clips-all %d/%d"
          % (kf_n, TOTAL, clip_n, TOTAL, all_n, TOTAL))
    print("目录：kv=%s ｜ clips=%s ｜ bank=%s"
          % (os.path.basename(KF), os.path.basename(CLIPS),
             os.path.basename(BANK) if BANK else "（未找到）"))

    pclip, _ = newest(CLIPS, r"shot_.*\.mp4$")
    a_clip = age_min(pclip)
    print("片段最新：%s（%s）" % (os.path.basename(pclip) if pclip else "无",
                              "%.1f 分钟前" % a_clip if a_clip is not None else "—"))

    pfrm, frm_n = newest(os.path.join(WORK, "out"), r".*\.jpg$")
    if frm_n:
        print("合成帧 %d 张 ｜ 最新 %.1f 分钟前" % (frm_n, age_min(pfrm)))

    mp4s = [os.path.join(ROOT, n) for n in os.listdir(ROOT) if n.endswith(".mp4")] \
        if os.path.isdir(ROOT) else []
    if mp4s:
        m = max(mp4s, key=os.path.getmtime)
        print("成片：%s（%.1f MB，%.1f 分钟前）" % (os.path.basename(m),
                                              os.path.getsize(m) / 1048576.0, age_min(m)))
        pa, _ = newest(ALL, r"shot_.*\.mp4$")
        if pa and os.path.getmtime(pa) > os.path.getmtime(m) + 1:
            issues.append("成片比 clips-all 里的输入片段旧（%s 新于 %s，差 %.0f 分钟）"
                          "→ 这版成片不含最新片段，属「假完成」"
                          % (os.path.basename(pa), os.path.basename(m),
                             (os.path.getmtime(pa) - os.path.getmtime(m)) / 60.0))

    mk = sorted(os.listdir(STATE)) if os.path.isdir(STATE) else []
    print("marker：%s" % (", ".join(mk) if mk else "无"))
    pl = procs()
    PROC_UNKNOWN = pl is None
    if PROC_UNKNOWN:
        # 2026-10-05：macOS/Linux 上曾因 creationflags 抛错被 except 吞掉 → 永远显示"（无）"，
        # 于是"生成器还在跑"被误报成"已停/崩"。现在取不到就明说，不让它冒充结论。
        print("进程：（**取不到进程列表**：进程查询命令不可用或被杀，进程类结论不可信）")
        issues.append("取不到进程列表 → 进程类判定（是否已停/疑似卡住）本轮不可信；"
                       "只看计数、新鲜度与一致性")
    else:
        print("进程：%s" % (", ".join("%s#%s" % t for t in pl) if pl else "（无）"))
    names = [t for t, _ in (pl or [])]
    has_gen = "生成器" in names
    has_driver = "驱动" in names
    has_compose = "合成" in names

    if TOTAL and clip_n < TOTAL and not has_gen and not PROC_UNKNOWN:
        issues.append("片段未齐（%d/%d）但没有生成器进程 → 已停/崩，需重启断点续跑" % (clip_n, TOTAL))
    if TOTAL and 0 < clip_n < TOTAL and has_gen and a_clip is not None and a_clip > 45:
        issues.append("片段停在 %d/%d、最新片段已 %.0f 分钟没动，但生成器进程还在 → 疑似卡住"
                      % (clip_n, TOTAL, a_clip))
    done_all = "DONE.ok" in mk and bool(mp4s)
    if TOTAL and clip_n >= TOTAL and all_n >= TOTAL and not has_compose and not has_driver and not done_all:
        issues.append("片段与 clips-all 都齐，但既没合成也没驱动 → 流程中断")
    if has_compose and frm_n and age_min(pfrm) > 20:
        issues.append("合成进程在跑，但合成帧已 %.0f 分钟没长 → 疑似卡住" % age_min(pfrm))

    # 一致性：state 里标 completed 的镜，磁盘上是否真有片段
    for sp in glob.glob(os.path.join(ROOT, "*gen-state.json")):
        try:
            st = json.load(io.open(sp, encoding="utf-8"))["shots"]
        except Exception:
            continue
        done = [k for k, v in st.items() if isinstance(v, dict) and v.get("status") == "completed"]
        miss = [k for k in done if not os.path.exists(os.path.join(CLIPS, "shot_%s.mp4" % k))]
        if miss:
            issues.append("state(%s) 标完成、磁盘上却没有片段：%s"
                          % (os.path.basename(sp), " ".join(miss[:8])))

    for name in sorted(os.listdir(ROOT)) if os.path.isdir(ROOT) else []:
        if not name.endswith((".out.log", ".err.log")):
            continue
        for ln in tail(os.path.join(ROOT, name)):
            if re.search(r"(Traceback|Error|FAILED|失败|HTTP 5\d\d)", ln):
                issues.append("%s 有异常行：%s" % (name, ln[:140]))
                break

    if issues:
        print("\n判定：发现 %d 处不对 ——" % len(issues))
        for i in issues:
            print("  · " + i)
        return 1
    if done_all and not pl:
        print("\n判定：已完成（DONE.ok + 成片都在，当前没有进程在跑——这是正常收尾状态）")
    else:
        print("\n判定：正常（计数、进程、新鲜度、一致性都对得上）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
