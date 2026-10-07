# Music MV Studio

![license](https://img.shields.io/badge/license-MIT%20%2B%20CC--BY--4.0-blue)
![type](https://img.shields.io/badge/type-Agent%20Skill-6f42c1)
![CI](https://github.com/chenqianshinian/music-mv-studio/actions/workflows/ci.yml/badge.svg)

**一个「音乐视频（MV）制作」的 Agent Skill**：把「一首歌 + 一份歌词」做成竖版音乐 MV 的可复用工作流——
导演方法 + 一条跑过多首长片（每首约 100 镜）的生成管线 + 66 条真实踩过的坑。

> 入口是 **[SKILL.md](SKILL.md)**：支持 Agent Skills 的工具（Codex 等）把它放进 skills 目录即可加载；
> 不装进 Agent 也能照做——它就是一份可执行的制作纪律 + 一组能独立运行的 Python 脚本。
>
> 这个仓库最值钱的部分不是脚本，是 SKILL.md 的 **§5 血泪清单**。
> 能跑的 AI 流水线很多；把「踩过什么坑、为什么、正确做法是什么」写下来的很少。

## 它不是黑盒

| 是 | 不是 |
| --- | --- |
| 一份可照做的**制作纪律**：什么必须先定、什么必须量、什么必须重出 | 输入歌名就自动出片的按钮 |
| 一条**可断点续跑**的管线：首帧闸门 → 逐镜生成 → 按帧号缓存的合成 → 像素级质检 → 定点返修 | 一个端到端训练好的模型 |
| 一套**验收方法**：用像素和数字下结论，而不是"看着还行" | 保证一次成功的魔法 |

## 30 秒看懂

```
分镜库 bank.json
      │
      ├─► ① 首帧 kf_<key>_0.png ──── 闸门：人数/朝向/画风/构图，用数字判，目视放行必出事
      │            │
      │            └─► ② 第二关键帧 kf1x（从首帧 i2i 派生，必须与首帧同人数同结构）
      │                        │
      │                        └─► ③ i2v 视频候选 shot_<key>_N.mp4 ──► 择优 shot_<key>.mp4
      │                                                                      │
      └─► 字幕 SRT / 逐句时间表 clauses.json ────────────────────────────────┤
                                                                             ▼
                                          ④ 合成：每帧写成 out/%05d.jpg，按帧号缓存
                                                                             │
                                          ⑤ 质检：字幕亮字占比 / 素材内部突变 / 方向与人数
                                                                             │
                                          ⑥ 定点返修：只把受影响的帧移走重画，其余复用
```

**第 ④ 步的"按帧号缓存"是省时间的关键**：整片 9000 帧，改字幕或换两三镜时只重画受影响的几十帧
（3–5 分钟），而全片重画要 40–60 分钟。

## 5 分钟跑通（零 API 费用、不需要密钥）

仓库自带一个**不调用任何模型**的示例：生成 4 段合成镜头 + 字幕 + 占位音轨，然后合成出一支短片。
先确认"片段 → 成片"这一段通，再去接真接口。

```bash
pip install numpy Pillow
python examples/make_demo_assets.py demo
```

示例体积：v3.0 的默认参数会产出 4×19MB 片段 + 88MB 成片，对"5 分钟跑通"偏重；v3.1 把码率与噪声
下调（CRF 22→24、噪声强度 12→8），默认参数下现在是每个片段约几 MB、成片约十几 MB 的量级。CI 用的是
`--fast`（每段 4 秒、CRF 28、弱噪声）——它只验证管线通不通，不追求画质；想改每段时长用 `--sec`。

按脚本打印的提示设好环境变量（Windows cmd 示例；macOS/Linux 把 `set` 换成 `export`、
路径分隔符换成 `/`）：

```bat
set ZDN_BANK=examples\song-a-bank.json
set ZDN_CLIPS=demo\clips
set ZDN_SRT=demo\song-a.srt
set ZDN_AUDIO=demo\song-a-tone.m4a
set ZDN_OUT=demo\song-a-mv.mp4
set ZDN_TOTAL=14.2
set ZDN_FADE_OUT=12,2
python scripts\compose_mv.py
```

自检：

```bash
python scripts/doctor.py                                            # 环境逐项检查
python scripts/qa_captions.py demo/song-a-mv.mp4 demo/song-a.srt 1580 140
python tests/smoke_offline.py                                       # 整条离线链路真跑一遍
```

`doctor.py` 会逐项给出"就绪 / 警告 / 阻塞"，字体一项是**真的把"中""永"两个字渲染一遍**再比对位图：
只确认"字体文件在不在"不够——字体缺字时字幕会画成豆腐块，而下面的 QA 只看亮像素，照样给出峰值。

`qa_captions` 应给每条 cue 一个明显峰值，并打印明确判定与退出码（`0` = 每条已检 cue 都有峰值 /
`1` = 低于判定下限 / `2` = 抽帧失败 / `3` = 没有一条 cue 落在成片时长内，判据不成立、不算通过）；
阈值 180 下出现 `0.00%` 时会**自动**降到 `140` 复测并打印两组数
（见 SKILL §7.4）。

`tests/smoke_offline.py` 则把"示例素材 → 合成 → 字幕 QA → 总览图 → 瞬现物检测"整条链路在本机真跑一遍
（9 项判定，不需要密钥、不调用任何模型），比单跑某一条命令更能说明"这台机器整条管线通不通"。

## 接真接口（要花生成费用 / 有速率限制）

```bash
cp .env.example .env       # 填 AGNES_API_KEY 等
python scripts/doctor.py
python scripts/gen_zuindongni.py --bank <你的分镜库.json> --outdir <中间产物目录> --kf-only
# 逐镜过 SKILL.md §4 的首帧闸门，过关后再去掉 --kf-only 出视频候选
```

接口这一层是**薄适配**：默认实现走一个兼容 OpenAI 风格的服务（图像 / 视频 / 视觉各一个模型名），
换供应商只需要改 `.env` 里的 `AGNES_BASE_URL` 与 `MV_*_MODEL`。
**注意：生成会消耗额度、可能受速率限制**，管线里的退避重试是为限流准备的，不是 bug。

`.env` 里与"接真接口"有关的还有上传这一组——i2i/i2v 接口只吃 URL，垫图必须先传到图床：

- `CURL_BIN`：上传用的 curl（默认 `curl`；Windows 10+ 自带，只是以前被写死成 `curl.exe`）。只跑
  `examples/` 的离线示例不需要它。
- `MV_UPLOAD_URL` / `MV_UPLOAD_FIELD`：图床地址与表单字段名。**默认是一家匿名公共图床
  （`https://uguu.se/upload`）：含人脸的关键帧会变成公开可访问的 URL**，介意就换成自己的
  （需要兼容 `curl -F <字段>=@文件 <URL>` 并返回 `{"files":[{"url":...}]}`）。
- `MV_UPLOAD_DISABLE=1`：离线自检时禁止上传；真到上传那一步会直接报错，而不是静默失败。

## 目录结构

```
.
├── SKILL.md                 # ★ 方法论与纪律（§5 = 66 条血泪清单）
├── README.md
├── CHANGELOG.md             # 每一版改了什么、为什么
├── CONTRIBUTING.md
├── .env.example             # 所有环境变量的模板
├── .github/workflows/ci.yml # CI：发布门禁 + 三平台离线冒烟 + markdown 检查
├── agents/openai.yaml       # skill 元信息（供支持 skill 的客户端读取）
├── references/              # 分节细读：分镜设计 / 提示词规范 / 关键帧策略 / QA 清单 / 管线
├── scripts/
│   ├── _mvcfg.py            # ★ 环境变量的唯一入口（其余脚本都从这里取）
│   ├── doctor.py            # 环境自检
│   ├── gen_zuindongni.py    # 生成器：首帧 → 派生帧 → i2v 候选（断点续跑）
│   ├── compose_mv.py        # 参考合成器：按帧号缓存 + 字幕 + 溶解 + 淡出
│   ├── status.py            # 进度/存活自检（计数·进程·新鲜度·一致性）
│   ├── qa_captions.py       # 字幕像素级校验
│   ├── check_transient.py   # 瞬现物（一闪即过的穿帮物）检测
│   ├── check_subject_track.py  # 主体"越走越小/折返"的像素判据
│   ├── still_move.py        # 确定性 2.5D 运镜（只做兜底与单镜返修）
│   ├── grab_frames.py       # 成片抽帧总览图
│   ├── kf_sheet.py          # 首帧总览拼图
│   └── ask_image.py / ask_multi.py   # 视觉复核（单张定向追问 / 多图对比）
├── examples/
│   ├── README.md            # 分镜库字段说明
│   ├── song-a-bank.json     # 脱敏示例分镜库（虚构歌名）
│   └── make_demo_assets.py  # 零成本示例素材生成器
├── tests/
│   └── smoke_offline.py     # ★ 零成本端到端冒烟测试（不联网、不需要密钥）
└── tools/
    ├── hygiene_scan.py      # ★ 发布门禁：扫密钥与个人绝对路径（含 macOS/Linux 用户目录）
    ├── portability_scan.py  # ★ 发布门禁：扫"只在 Windows 上能跑"的写法
    └── sanitize_secrets.py  # 批量把明文密钥改成读环境变量
```

## 三条最重要的纪律

如果只记得三件事，记这三条（其余见 [SKILL.md](SKILL.md) §5）：

1. **闸门要"量"不要"看"。** 首帧必须让视觉模型给出**数字**：几个人、占画面几分之几、朝向哪边、有没有脸。
   目视放行是我们踩得最狠的坑（目视"过关"的镜头实测两人占画面 1/2，设计要求 ≤1/10）。
2. **结论一律以单张全尺寸为准。** 拼图和缩略图会让视觉模型幻觉出并不存在的文字和人数；
   几何二次加工图（裁切/拼图/缩放）不能作为定性依据——与可复算的像素证据冲突时，以像素为准。
3. **同一问题换 2 次机制仍复发 ⇒ 改设计，不要继续抽卡。** 减少主体数量、缩小主体占比、
   换成同场景里已经干净的素材——这类零生成成本的修法优先。

## 跨平台

支持 Windows / macOS / Linux，三者都进 CI 的 `smoke` job。

v3.0 的问题**不是"没打算跨平台"，而是只在 Windows 上被验证过**：7 个脚本把 Windows 专有的
creationflags（`0x08000000`）直接传给 `subprocess`，在 macOS/Linux 上会抛
`ValueError: creationflags is only supported on Windows platforms`；生成器还写死了 `curl.exe`、
`ffprobe.exe`、`NUL`。作者的提交环境是 Windows，这些在本地一个都看不到——README"5 分钟跑通"里
那条 `qa_captions` 自检就正好踩在其中一个上。

v3.1 的修法：

- **平台差异集中到 `scripts/_mvcfg.py` 的 `NO_WIN`**（Windows 下 `0x08000000`，其它平台 `0`），
  可执行名一律走 `FFMPEG_BIN` / `FFPROBE_BIN` / `CURL_BIN`，公共代码路径里不再出现 Windows 专有常量；
- **字体按平台自动探测**：macOS 苹方 / 冬青黑 / 华文黑体，Windows 雅黑 / 黑体 / 思源，
  Linux Noto CJK / 文泉驿；并且用真渲染"中""永"两个字、比对位图的方式确认它**真的**能画中文
  （缺字时两个字都画成同一个方框，位图相同）。正式出片仍建议用 `MV_FONT_BRUSH` 指向自己的
  OFL 等可商用授权字体（见 SKILL §5 #5）；
- **两条静态门禁**（`hygiene_scan.py`、`portability_scan.py`）拦"只在 Windows 上能跑"的写法，
  **再加一条在非 Windows 上真跑整条管线的 `tests/smoke_offline.py`**——`compileall` 与静态扫描
  抓不到这一类问题，只有真跑一遍才行（见 SKILL §5 #42/#43）。

## 依赖与成本

- **依赖**：Python 3.10+、`numpy`、`Pillow`、`ffmpeg`（含 ffprobe）；**只有走真接口才需要 `curl`**
  （上传垫图用，默认走 PATH，可用 `CURL_BIN` 指定）。没有额外 SDK。
- **生成成本**：由你使用的接口决定。经验口径——串行 1–2 路最稳，约 2–4 分钟/镜；
  并行度开到 4 会同时吃限流、**总吞吐反而更低**。
- **时间成本**：一次"定点返修"的主要开销是合成而不是生成，所以**同批问题攒起来一次改完**
  （这也是一条纪律，见 SKILL §9）。

## 接口与兼容性

脚本用标准库 `urllib` 调三类 **OpenAI 风格**的 HTTP 接口，所以**任何兼容这三类接口的网关都能用**，
换供应商只改 `.env`，代码一行都不用动（垫图上传走 `curl`，见表格最后一行）：

| 用途 | 接口 | 环境变量 |
| --- | --- | --- |
| 首帧 / 第二关键帧 | `POST /v1/images/generations` | `MV_KF_MODEL`、`MV_I2I_MODEL` |
| 图生视频 | `POST /v1/videos` ＋ 轮询任务状态 | `MV_I2V_MODEL` |
| 视觉复核（数人头、判画风） | `POST /v1/chat/completions`（多模态） | `MV_VISION_MODEL` |
| 垫图上传（i2i / i2v 的输入是 URL） | 表单 `POST` 到 `MV_UPLOAD_URL`（用 `curl`） | `MV_UPLOAD_URL`、`MV_UPLOAD_FIELD`、`MV_UPLOAD_DISABLE` |

图床那一行的默认值是**匿名公共图床**：含人脸的关键帧会变成公开可访问的 URL，介意就换成自己的图床，
离线自检用 `MV_UPLOAD_DISABLE=1` 关掉上传。

`.env.example` 里的默认地址与模型名，是我做这些 MV 时实际使用的服务商（Agnes AI，`apihub.agnes-ai.cn`）；
写上去只是为了让仓库**开箱可跑**。本项目与任何模型服务商都**没有隶属、赞助或背书关系**，
各模型的能力、额度、计费与素材授权请以服务商自己的条款为准。
（密钥变量名沿用 `AGNES_API_KEY`，纯属历史命名，换成其它供应商照样用。）

## 常见问题

**Q：一定要用某个模型服务吗？**
不需要。默认实现是"兼容 OpenAI 风格的图像/视频/视觉接口"这一层薄适配，`.env` 里换地址和模型名即可。

**Q：为什么没有我需要的某个脚本？**
这个仓库只收录**与题材无关、已稳定复用**的部分。合成器与质检脚本是从真实项目里抽出来的通用版；
与具体歌曲绑定的一次性脚本（分镜库生成、某个镜的专项返修）不适合入库。

**Q：可以把我的成片/素材提上来吗？**
不要。音频、成片、真人肖像、字体文件都不入库（`.gitignore` 已覆盖常见后缀）。

## 授权

- **代码**（`scripts/`、`tools/`、`examples/*.py`）：[MIT](LICENSE)
- **文档**（`SKILL.md`、`references/`、`README.md`、`CHANGELOG.md`、`CONTRIBUTING.md`）：[CC BY 4.0](LICENSE-docs.md)

---

## English summary

**Music MV Studio** turns a song plus its lyrics into a vertical music video.
It is a *methodology plus a production pipeline*, not a black box:

1. **Lock the design first** — director's five layers and a per-song questionnaire (SKILL §0–§2).
2. **Gate every first keyframe with numbers, not eyes** — how many people, what fraction of the frame,
   which way they face (SKILL §4).
3. **Generate per shot** — first keyframe → derived second keyframe (i2i) → i2v candidates,
   with explicit direction / structure / motion locks in the prompt (SKILL §6).
4. **Verify with pixels** — caption pixels, in-clip scene cuts, subject scale sequences (SKILL §8).
5. **Repair surgically** — the composer caches frames by frame index, so a fix re-renders tens of frames
   instead of the whole film (SKILL §3, §9).

The most valuable file is [SKILL.md](SKILL.md) §5: **45 lessons actually paid for in production**.
Try it for free first: `python examples/make_demo_assets.py demo` needs no API key.

A zero-cost offline smoke test (`tests/smoke_offline.py`) runs the same pipeline on Linux, macOS and
Windows in CI, so a change that only works on one platform no longer lands silently.

Code is MIT; documentation is CC BY 4.0.
