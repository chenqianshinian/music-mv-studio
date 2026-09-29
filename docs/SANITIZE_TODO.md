# 发布前待清理清单（脚本化，可复查）

生成方式：`python tools/hygiene_scan.py`
现在状态：**明文密钥 0 处**（已由 `tools/sanitize_secrets.py` 改成读环境变量）；
**个人/机器绝对路径 33 处**，逐条列在下面。

## A. 脚本（22 处，手法统一：改成 `os.environ.get(...)` + 默认值）

| 文件 | 行 | 内容 |
|---|---|---|
| scripts/ask_image.py | 6 | `WORK = C:\Users\...\ni\work` |
| scripts/ask_multi.py | 20 | 同上 |
| scripts/lianan_kf_sheet.py | 14,15 | WORK / 输出目录 |
| scripts/mv_status.py | 18 | `E:\MV-temp` |
| scripts/gen_zuindongni.py | 23,248 | FFMPEG 目录 / 默认输出目录 |
| scripts/check_transient.py | 23 | FFMPEG 目录 |
| scripts/check_a318_dir.py | 17,18 | FFMPEG 目录 / 临时帧目录 |
| scripts/qa_captions.py | 17,38 | FFMPEG 目录 / 默认工作目录 |
| scripts/grab_frames.py | 10,11 | FFMPEG 目录（两个） |
| scripts/still_move.py | 21 | FFMPEG 目录 |

统一约定：
- `FFMPEG_BIN`（默认 `ffmpeg`，走 PATH）
- `MV_WORK`（默认 `./work`）
- `MV_TMP`（默认 `./tmp`）
- 其余写死的歌名目录 → 改成命令行参数

## B. 文档（11 处）

| 文件 | 行 | 说明 |
|---|---|---|
| SKILL.md | 81, 151, 152, 246 | `C:\Users\...` 示例路径 |
| SKILL.md | 123, 150, 153, 154, 246, 2xx | `E:\MV-temp` / `D:\om-setup` / `D:\CodexMemory` / 歌库路径 |
| references/pipeline.md | 8, 21 | 同上 |
| references/keyframe-strategy.md | 33 | `D:\om-setup` |

注意：`SKILL.md:246-247` 命中的是 **§10 这份检查清单本身的正文**（它逐个列举了要删的路径）。
公开版会把 §10 整节重写为「发布门禁：怎么跑 tools/hygiene_scan.py」，不再逐条列举私有路径。

## C. 还没做的（不在扫描范围，但同样属于发布门槛）

1. provider 适配层（把 Agnes 抽成示例实现，见 §10.1 第 4 条）。
2. 脱敏示例：虚构歌名的最小 bank JSON + 示意图（不含真实歌曲、音频、清晰正脸）。
3. 工程四件：`LICENSE`、`README.md`、`CONTRIBUTING.md`、`CHANGELOG.md`。
4. `agents/openai.yaml` 转存为 **UTF-8**（现在这份是 GBK，别人机器上会乱码）。
5. 「另一台电脑从零跑通」验收：按 README 走完"一张首帧 → 一段镜头 → 一小段合成"。
