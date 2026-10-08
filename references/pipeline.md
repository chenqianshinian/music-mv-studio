# 管线细读：脚本职责、断点续跑、新歌接入

## 1. 一次完整的跑法

```
# ⓪ 先确认机器能跑（换机器/新环境第一件事）
python scripts/doctor.py            # 平台 / 依赖 / ffmpeg / curl / 字体（真渲染中文）/ 密钥
python tests/smoke_offline.py       # 可选：零成本端到端冒烟，一次跑完 9 项

# ① 写分镜库（字段见 examples/song-a-bank.json，字段说明见 examples/README.md）

# ② 只出首帧，过闸门
python scripts/gen_zuindongni.py --bank <bank>.json --outdir <outdir> --kf-only
#    -> <outdir>/*-kv-frames/kf_<key>_0.png  +  kf1x_<key>.png
#    逐镜过 SKILL §4 的六项（人数/画风/畸形/文字/朝向/构图），不合格按 §4 的五类对症修

# ③ 出视频候选（去掉 --kf-only）
python scripts/gen_zuindongni.py --bank <bank>.json --outdir <outdir>
#    -> <outdir>/*-mv-clips/shot_<key>_<n>.mp4（每镜 N 个候选）

# ④ 逐镜择优：素材内部突变 / 瞬现物 / 方向与人数 / 与规格一致
python scripts/check_transient.py <候选.mp4> --lo 0.65 --hi 4.30
#    选中的复制成 clips-all/shot_<key>.mp4（旧版移进备份目录，不要删）

# ⑤ 合成
python scripts/status.py                      # 先看四类事实，别凭感觉
python scripts/compose_mv.py                  # 需要 ZDN_BANK/ZDN_CLIPS/ZDN_OUT
#    片段被换过而帧缓存还是旧的 → 会打印受影响的镜与帧号区间；
#    交付前可加 --strict-cache：不一致直接退出码 1，拒绝出一版过期成片

# ⑥ 质检 → 定点返修
python scripts/qa_captions.py <成片> <srt> 1580 140   # 有判定与退出码（0/1/2/3）
python scripts/grab_frames.py <成片> 总览.jpg 30 6
```

**换平台时**：脚本里的平台差异全部来自 `scripts/_mvcfg.py`（`NO_WIN` / `FFMPEG` / `FFPROBE` /
`CURL` / `NULL_DEVICE`）。不要在任何业务脚本里再写 Windows 专有常量或 `*.exe` 名字，
`python tools/portability_scan.py` 会拦住；CI 在 ubuntu / macOS / Windows 三平台各跑一次
`doctor.py` + `smoke_offline.py`（§5 #42/#43）。

## 2. 断点续跑与状态文件

- 生成器把每个镜的进度写进 `<outdir>/<bank 名>-gen-state.json`，重跑自动跳过已完成。
- **多路并行**：`--t0-min/--t0-max` 切时间段，配合 `--state-tag` 给每路一个独立后缀
  （每路一个 state 文件，互不覆盖）。降并行度时合并 state 即可无缝接管。
- **改素材前必须先处理 state**：只把旧素材移走、不清 state，生成器会把旧任务结果重新下载一遍，
  交付出"看起来新、其实旧"的成片（SKILL §5 #8）。

## 3. 新歌接入（八步）

1. 过 SKILL §0 的「每首歌必答」，把风格/视角/结构定下来，**不要沿用上一首的默认值**；
2. **核对唱词**：用户给的歌词文档 **≠** 实唱词——先跑歌词校准（SKILL §7.6），
   把差异行交用户确认；**确认为真源之后**再往下写命题表与 SRT，否则字幕和画面命题都要返工；
3. 写导演五层（SKILL §2），再写分镜库；
4. `--kf-only` 出首帧 → 过闸门（§4）；
5. 出视频候选 → 择优（§8 的第 8/10 条），并做**片段级复核**（§8 第 19 条）；
6. 备好 SRT；若要做**逐句揭示**，先产出 `clauses.json`（§7.1），并逐条核**单屏 ≤12 汉字**（§7.5）；
7. 合成 → 质检（§8 逐条）；
8. 交付前跑一遍 §8 的完整清单，把本轮新踩的坑补进 §5 与 §10。

## 4. 已知坑（长期有效）

- **图床 URL 会失效**：上传图片后必须逐个校验可达（偶发 404），失效要重传——
  否则生成任务会拿到一个坏链接、静默失败。默认图床是**匿名公共**的（`MV_UPLOAD_URL`），
  含人脸的关键帧会变成公开可访问的 URL；要私有化就换自建图床。
- **队列满载**：接口返回"队列满/503"时用小退避循环重试（每 5 分钟一次），
  但**不要同时开多个生成器写同一个 state 文件**（会互相踩）。
- **ffmpeg 的音轨流编号**：某些版本里 `[1:a]` 这类通配符绑定会失败，用 `[1:0]` 数字编号。
- **交叉淡化取"下一段帧"时，局部时间必须钳到 ≥0**，否则索引为负直接崩溃。
- **大目录不要用某些运行时自带的递归拷贝**：几 GB 的素材目录会让它崩（Windows 上有过
  0xC0000005）。用系统自带的 `Copy-Item` / `cp -r`。
- **抽帧质检的窗口要按分镜库反算**：`帧号 = 秒 × 30`，区间是
  `[t0 − LEAD, t1 + DISSOLVE]`。**不要用"素材前 3.3s"这类习惯值**——
  曾经因为默认窗口太短，漏掉了整条素材的后 1/3，放过了三条带缺陷的候选。
