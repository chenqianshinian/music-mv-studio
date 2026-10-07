# 贡献指南

这个项目的价值一半在代码、一半在**经验记录**。所以贡献分两类：改脚本，或者补经验。

## 绝对不要提交的东西

| 不要提交 | 为什么 |
| --- | --- |
| **密钥**（任何形式的明文 token / key） | 一律走环境变量或 `.env`（已在 `.gitignore`）。提交前跑 `python tools/hygiene_scan.py` |
| **个人或机器的绝对路径**（本机用户目录、某块数据盘下的私有工作目录） | 换台机器就跑不了。所有路径走 `scripts/_mvcfg.py` 提供的环境变量 |
| **素材**：音频、成片、真人肖像、字体文件 | 版权与隐私风险。示例用虚构素材（见 `examples/`） |
| 几 GB 的帧缓存 / 中间产物 | `.gitignore` 已覆盖；确认没被 `git add -f` 强加进去 |

发布门禁（CI 也会跑，本地先跑一遍能省一次往返）：

```bash
python tools/hygiene_scan.py        # 密钥 + 个人/机器绝对路径；有命中就退出码 1
python tools/portability_scan.py    # 只在 Windows 上能跑的写法；有命中就退出码 1
python -m compileall -q scripts tools examples tests
python tests/smoke_offline.py       # 非 Windows 上真跑一遍离线管线；零成本、不需要密钥
```

三条静态门禁各拦一类：`hygiene_scan.py` 拦**密钥与个人/机器绝对路径**（这类东西一进仓库，
别人换台机器就跑不了）；`portability_scan.py` 拦 **Windows 专有写法**（`creationflags`、
写死的 `*.exe`、`"NUL"`、盘符路径）——它们在 Windows 上完全正常，到 macOS/Linux 上就是
`ValueError`，静态扫描是唯一能在合并前拦住它的地方；`compileall` 只查语法。
`tests/smoke_offline.py` 是动态门禁：它在**非 Windows** 上真跑一遍离线管线（示例素材 → 合成 →
字幕 QA → 总览图 → 瞬现物检测 → 字体能不能画中文），静态门禁看不见的运行时故障只有它会当场翻红。

## 改脚本

- **路径与密钥只能有一个入口**：复用 `scripts/_mvcfg.py`，不要自己再写一套解析。
- **跨平台**：不要引入 Windows 专有的常量或命令——`creationflags`、`curl.exe`、`NUL`、
  盘符路径这类写法要么在 macOS/Linux 上直接抛错、要么静默走错分支，而 Windows 本机自测
  一个都看不出来。可执行文件、空设备与子进程常量一律复用 `scripts/_mvcfg.py` 的
  `NO_WIN` / `FFMPEG` / `FFPROBE` / `CURL` / `NULL_DEVICE`。
  确有必要保留的 Windows 分支（例如 `os.name == "nt"` 里的 powershell 调用）在该行或上一行
  写 `# portability-scan-allow: 理由`，让 `portability_scan.py` 放行；豁免要写清理由，
  别拿它盖住本来好写的跨平台改法。
- **新增一个能跑的脚本，就顺手更新三处**：`README.md` 的目录结构、`SKILL.md` §3 的工具表、
  以及 `.env.example`（如果你引入了新的环境变量）。
- **任何自检/判据类脚本，必须在 PR 里说明你用哪条已知样本回测过。**
  这是踩坑后立的规矩：改个缩进导致台账少报；取个默认窗口就漏掉整条素材的后 1/3。
  自检脚本"看起来对"和"确实对"是两件事。
  改的是**门禁/自检类脚本**（`tools/*_scan.py`、`scripts/qa_captions.py`、合成器的缓存判据……）时，
  还要跑一遍 `python tests/smoke_offline.py`：它是唯一一条在非 Windows 上真跑管线的门禁，
  你改的判据如果只在 Windows 上成立，只有它会当场翻红。
- **不要引入新的运行时依赖**，除非真的不可替代（目前只有 `numpy` 与 `Pillow`）。
- **本地最低验证 = 三条门禁 + `python tests/smoke_offline.py`**：上面那条门禁块
  （`hygiene_scan` / `portability_scan` / `compileall`）几秒钟跑完，冒烟测试在本机约 27 秒
  （macOS 实测 9/9 通过）。改完先自己跑一遍，比把 CI 等一轮再回来改便宜得多。

## 补经验（更欢迎这一类）

- **踩到新坑**：在 `SKILL.md` §5 血泪清单**末尾追加一条**（现在到 #66，编号连续，不要插队），
  写清三件事：**现象**（观众看到什么）、**为什么**（查证到的根因，有数据最好）、
  **正确做法**（可执行的动作）。不要只写"不要这样做"。
- **推翻了旧结论**：在 §10「已被推翻的结论」加一行——写清"曾经的结论 / 为什么被推翻 / 现行口径"。
  这比新增一条更有价值：**它防止别人重新走一遍你已经走过的错路。**
- **改了某条规则**：同一次提交里把文档与示例一起改，不要只改一头。
- **引用外部项目**：说明借鉴了什么、哪些明确不采纳、为什么。不许含糊的"参考了某某"。

## 提交信息

一句话说清"改了什么 + 为什么"，例：

```
合成器：把按帧号缓存的说明提到文件头

原来只写在 SKILL 里，单独看脚本的人不知道 --fresh 会清掉 9000 帧缓存。
```

## 关于示例内容

示例必须**虚构且可公开**：不要用真实歌名/歌词/艺人肖像，不要含可识别的真人正脸。
音频用合成音（`examples/make_demo_assets.py` 里的正弦波就是范例）。

## 授权

提交即表示你同意：代码以 [MIT](LICENSE)、文档以 [CC BY 4.0](LICENSE-docs.md) 授权。
