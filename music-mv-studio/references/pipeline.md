# 流水线脚本复用说明

> **2026-09-24 更正（v2.1）**：本文件下面的"脚本位置/新歌接入步骤"写于 2026-08，指向的是**已过期**的 `gen_shots_agnes.py`（含明文密钥、无首帧闸门/人物卡/i2i 派生帧/分段并行），不要再照它做新歌。**当前有效实现见 SKILL.md §3 执行层**（`gen_zuindongni.py` / `compose_<歌名>.py` / `run_<歌名>.py` / `mv_status.py` / `pick_v4d.py` / `check_clip_heads.py`，都从会话 `work\` 取，不要跨会话乱指路径）。下面内容保留作历史参考，其中「已知坑」一节的 uguu 图床、503 守护、ffmpeg `[1:0]` 编号等条目仍然有效。

## 脚本位置（会话 work 目录，2026-08 版本）

```
C:\Users\Huangzelong\Documents\Codex\2026-08-02\obsidian-codex-agent\work\
├── gen_shots_agnes.py      # 批量生成器（关键帧+多候选+keyframes模式+断点续跑）
├── check_timeline.py       # 渲染前检查（镜头唯一/风格账本/素材健康）
├── stroke_render.py        # 书法挥毫字幕渲染器（志莽行书 glyph 模式）
├── make_<歌名>_bank.py     # 镜头库生成器（角色卡+分镜+提示词组装）
├── compose_<歌名>.py       # 合成器（帧级渲染+交叉淡化+字幕+音效混音）
└── supervise_<歌名>.ps1    # 守护循环（生成器崩溃自动重启）
```

## 新歌接入步骤

1. 写 `make_<歌名>_bank.py`（分镜 40 段内，每镜 2-3 关键帧）
2. `python make_<歌名>_bank.py` 生成 bank JSON
3. `python gen_shots_agnes.py --bank <歌名>_shot_bank.json --outdir D:\om-setup --candidates 3`
4. 写 `compose_<歌名>.py` + `styles_<歌名>.json`
5. `python check_timeline.py compose_<歌名>.py --style-json styles_<歌名>.json`
6. `python compose_<歌名>.py --fresh`（帧渲染 + 编码）
7. QA（见 qa-checklist.md）→ 交付 outputs + E 盘

## 已知坑（2026-08 实测）

- ffmpeg 8.1 的 `[1:a]` 流通配符绑定失败 → 用 `[1:0]` 数字编号
- 重启后 PATH 可能指向 Python3.10 → 需要 `pip install svgpathtools`（依赖 stroke_render）
- 交叉淡化取"下一段帧"时局部时间必须钳制 ≥0，否则索引负数崩溃
- Agnes 免费队列满载时（503 video_queue_full）：守护循环每 5 分钟重试，勿并发多个生成器（状态文件竞争）
- 图床 uguu URL 偶发 404：上传后逐个 curl 验证，失效重传
- Node fs.cpSync 复制大目录会崩溃（0xC0000005）→ 剪映草稿安装用 PowerShell Copy-Item
