# -*- coding: utf-8 -*-
"""零成本端到端冒烟测试：**在任何平台上真跑一遍管线**，不需要密钥、不调用任何模型。

它兜的是 v3.0 暴露出来的那类 bug：代码在 Windows 上全绿，换到 macOS/Linux 直接崩
（Windows 专有的 subprocess 常量、写死的 curl.exe / NUL、找不到 CJK 字体……），而单跑
`compileall` + `hygiene_scan` 一个都抓不到。

跑的东西（全部用本机 ffmpeg 合成，不联网）：

  ① 示例素材    examples/make_demo_assets.py --fast
  ② 合成        scripts/compose_mv.py --until 7.8（前两镜，含溶解与字幕）
  ③ 字幕 QA     scripts/qa_captions.py  → 每条已检 cue 必须有峰值
  ④ 总览图      scripts/grab_frames.py
  ⑤ 瞬现检测    scripts/check_transient.py
  ⑥ 字体自检    _mvcfg.resolve_font() 必须找到**能画中文**的字体（否则字幕是豆腐块）
  ⑦ 片段清单    compose 第二次跑必须命中缓存（不重复抽帧），改片段后必须报警

用法：python tests/smoke_offline.py [--keep] [--verbose]
退出码：0 = 全过；1 = 有失败项
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

KEEP = "--keep" in sys.argv
VERBOSE = "--verbose" in sys.argv
UNTIL = 7.8

results = []


def step(name, ok, detail=""):
    results.append((name, ok, detail))
    print("  [%s] %-34s %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)


def run(argv, env, timeout=600):
    # 子脚本的 stdout 编码并不统一：有的把自己重配成 utf-8（qa_captions / check_transient），
    # 有的沿用系统区域（中文 Windows 上是 GBK，例如 compose_mv）。父进程按任一固定编码解码，
    # 总有一半对不上：按 GBK 解会在读取线程抛 UnicodeDecodeError 并吞掉输出，按 UTF-8 解则是乱码。
    # 所以在这里把编码**约定死**：强制子进程按 UTF-8 输出，父进程按 UTF-8 解码。
    env = dict(env, PYTHONIOENCODING="utf-8")
    r = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    if VERBOSE or r.returncode != 0:
        tail = "\n".join((r.stdout or "").splitlines()[-12:] +
                         (r.stderr or "").splitlines()[-12:])
        print("    $ %s\n      exit=%s\n%s" % (" ".join(argv), r.returncode,
                                               "\n".join("      " + x for x in tail.splitlines())))
    return r


def main():
    t0 = time.time()
    work = tempfile.mkdtemp(prefix="mv_smoke_")
    demo = os.path.join(work, "demo")
    print("冒烟测试工作目录：%s%s" % (work, "（--keep 保留）" if KEEP else ""))

    env = dict(os.environ)
    env.update({
        "MV_WORK": os.path.join(work, "work"),
        "MV_TMP": os.path.join(work, "tmp"),
        # 显式清掉可能从外部继承来的密钥/字体/图床设置，保证"零成本、可复现"
        "AGNES_API_KEY": "",
        "MV_FONT_BRUSH": os.environ.get("MV_FONT_BRUSH", ""),
    })

    py = sys.executable

    # ⑥ 字体自检放最前面：字幕渲染不出来时后面的 QA 会假绿，先确认地基
    try:
        from _mvcfg import font_can_cjk, resolve_font
        font = resolve_font(os.environ.get("MV_FONT_BRUSH") or None)
        step("字体可画中文", bool(font) and font_can_cjk(font), str(font))
    except Exception as e:  # pragma: no cover
        step("字体可画中文", False, "resolve_font 抛错：%s" % e)

    # ① 示例素材
    r = run([py, "examples/make_demo_assets.py", demo, "--fast"], env)
    step("生成示例素材", r.returncode == 0 and os.path.isdir(os.path.join(demo, "clips")),
         "exit=%s" % r.returncode)

    env.update({
        "ZDN_BANK": os.path.join(ROOT, "examples", "song-a-bank.json"),
        "ZDN_CLIPS": os.path.join(demo, "clips"),
        "ZDN_SRT": os.path.join(demo, "song-a.srt"),
        "ZDN_AUDIO": os.path.join(demo, "song-a-tone.m4a"),
        "ZDN_OUT": os.path.join(demo, "song-a-mv.mp4"),
        "ZDN_TOTAL": "14.2",
        "ZDN_FADE_OUT": "5.8,2",
    })

    # ② 合成（只前 7.8 秒：够覆盖两镜、一次交叉溶解与两条字幕）
    r = run([py, "scripts/compose_mv.py", "--until", str(UNTIL)], env)
    mv = env["ZDN_OUT"]
    step("合成前 %.1fs 成片" % UNTIL,
         r.returncode == 0 and os.path.exists(mv) and os.path.getsize(mv) > 20000,
         "exit=%s, %s" % (r.returncode,
                          "%.1f MB" % (os.path.getsize(mv) / 1048576.0) if os.path.exists(mv) else "无输出"))

    # ③ 字幕 QA（cue 3/4 超出片长应被跳过，而不是判失败）
    r = run([py, "scripts/qa_captions.py", mv, env["ZDN_SRT"], "1580", "140"], env)
    step("字幕 QA", r.returncode == 0, "exit=%s" % r.returncode)

    # ④ 总览图
    sheet = os.path.join(work, "overview.jpg")
    r = run([py, "scripts/grab_frames.py", mv, sheet, "12", "4"], env)
    step("成片总览图", r.returncode == 0 and os.path.exists(sheet),
         "%s" % ("%.0f KB" % (os.path.getsize(sheet) / 1024.0) if os.path.exists(sheet) else "无输出"))

    # ⑤ 瞬现检测（拿第一段素材跑，合成用的窗口内应无瞬现物）
    r = run([py, "scripts/check_transient.py", os.path.join(demo, "clips", "shot_A1-1.mp4"),
             "--lo", "0.0", "--hi", "3.5"], env)
    step("瞬现物检测", r.returncode == 0, "exit=%s" % r.returncode)

    # ⑦ 片段清单：第二次合成必须命中缓存（不重复抽帧）
    manifest = os.path.join(env["MV_WORK"], "compose", "clips-manifest.json")
    keys_before = set(json.load(open(manifest, encoding="utf-8"))) if os.path.exists(manifest) else set()
    r = run([py, "scripts/compose_mv.py", "--until", "4.0"], env)
    step("片段签名清单已写出", len(keys_before) >= 2, "记录 %d 个片段" % len(keys_before))
    step("帧缓存复用（不重抽片段）",
         r.returncode == 0 and "重建帧来源" not in (r.stdout or ""),
         "exit=%s" % r.returncode)

    # ⑦b 片段变了必须报警：不报警就会交出"新片段进不了成片"的旧成片（§5 #15）
    clip = os.path.join(demo, "clips", "shot_A1-1.mp4")
    if os.path.exists(clip):
        with open(clip, "ab") as f:      # 只改 size/mtime，不需要真的重编码
            f.write(b"\0" * 64)
        r2 = run([py, "scripts/compose_mv.py", "--until", "2.0", "--strict-cache"], env)
        step("片段变更时 --strict-cache 拒绝出片",
             r2.returncode != 0 and "strict-cache" in (r2.stdout or "") + (r2.stderr or ""),
             "exit=%s" % r2.returncode)

    dt = time.time() - t0
    bad = [n for n, ok, _ in results if not ok]
    print("\n冒烟测试：%d/%d 通过，用时 %.1fs" % (len(results) - len(bad), len(results), dt))
    if bad:
        print("失败项：" + "、".join(bad))
    if not KEEP:
        shutil.rmtree(work, ignore_errors=True)
    else:
        print("工作目录保留在：%s" % work)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
