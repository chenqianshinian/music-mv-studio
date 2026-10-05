# 发版检查清单（维护者用）

每一次对外发版（打 tag / 宣布版本）之前，逐条过一遍。

## 1. 自动门禁（必须全绿）

```bash
python tools/hygiene_scan.py        # 密钥 + 个人/机器绝对路径；有命中就退出码 1
python tools/portability_scan.py    # 只在 Windows 上能跑的写法；有命中就退出码 1
python -m compileall -q scripts tools examples tests
python tests/smoke_offline.py       # 零成本离线端到端冒烟；不需要密钥
```

CI 会跑同样四条，外加 markdown lint。其中 `smoke_offline.py` 那一 job 在
ubuntu / macOS / Windows 三个平台上各跑一遍（Linux 另装 `fonts-noto-cjk`），
所以"这份代码只在 Windows 上能跑"这类问题不会再漂到发版前。本地先跑一遍能省一次往返。

`hygiene_scan.py` 扫这几类：`sk-…` 形式的明文密钥、`Bearer …`、`C:\Users\<用户名>`、
`<盘>:\MV-temp` / `<盘>:\om-setup` / `<盘>:\CodexMemory` 这类个人目录、个人歌库路径，
以及 **macOS/Linux 的个人目录**（`/Users/<真实用户名>`、`/home/<真实用户名>`，
和 `/Volumes`、`/mnt`、`/media` 下的私有数据盘）——v3.0 只扫 Windows 风格路径，
往 `scripts/` 里放一条 `/Users/<真实用户名>/…` 仍报 0 处命中。命中后**不要直接删那一行**——
把它改成环境变量读取（`scripts/_mvcfg.py` 已经提供 `get()` / `api_key()`），否则功能会被改坏。

## 2. 人工检查（自动门禁覆盖不到）

- [ ] **换机器的验收**：CI 已在 ubuntu / macOS / Windows 三平台自动跑离线示例；
      本地换机器时仍建议手动跑一次 `python tests/smoke_offline.py`，
      确认"`examples` 零成本示例 → 出成片"全程不需要任何个人路径与密钥。
- [ ] **字体真的能画中文**：`python scripts/doctor.py` 的字体项必须是 OK——
      PIL 找不到 CJK 字体会退化成缺字方框，而 `qa_captions.py` 只数字幕带里的亮像素，
      会**假报"有字幕"**。找不到能画中文的字体是**阻塞项**，不是警告。
- [ ] **`.env` 模板没有把注释写在值的后面**：`.env.example` 里注释独占一行，
      没有 `MV_KF_MODEL=…  # 注释` 这种写法——照抄模板的人会把注释一起当模型名发出去。
- [ ] **示例可公开**：`examples/` 里没有真实歌名、真实歌词、可识别的真人正脸。
- [ ] **文档与脚本一致**：`README.md` 的目录结构、`SKILL.md` §3 的工具表、
      `.env.example` 三处与实际文件对得上（新增/删除脚本最容易漏）。
- [ ] **示例仍在跑**：`examples/make_demo_assets.py` 生成的素材能被当前的
      `scripts/compose_mv.py` 合成出片（脚本接口改过就必须重跑一次）。
- [ ] **血泪清单与 §10 已更新**：这一轮的新坑写进 §5（编号连续），
      被推翻的旧结论写进 §10。
- [ ] **CHANGELOG 已更新**，并写清"这一版改了什么、为什么"。
- [ ] **LICENSE 与版权行**：代码 MIT、文档 CC BY 4.0；`LICENSE` 里的版权人
      与仓库所有者一致。

## 3. 已知的"不适合入库"清单（长期）

以下内容**永远不要**进仓库，无论什么理由：

1. 任何音频/成片/真人肖像/字体文件；
2. 与某首歌强绑定的一次性脚本（分镜库生成器、单镜专项返修脚本）——
   它们包含那个项目的具体文案，脱敏后就没有意义；
3. 逐镜的提示词全文（那是创作内容，不是方法）。

## 4. 怎么判断"可以发了"

用一句话自问：**一个陌生人能不能只靠 README 就在自己机器上跑出第一支短片，
并且知道遇到问题该查 SKILL 的哪一节？**

能，就发。
