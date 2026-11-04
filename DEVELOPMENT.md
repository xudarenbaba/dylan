# dylan 项目开发说明

| 项 | 内容 |
| --- | --- |
| 文档编号 | DYLAN-DEV-001 |
| 版本 | 0.2 |
| 状态 | 与需求规格 0.3、技术设计 0.2 对齐 |
| 日期 | 2026-11-03 |
| 上位文档 | [REQUIREMENTS.md](REQUIREMENTS.md)、[TECHNICAL.md](TECHNICAL.md) |
| 读者 | 实现者 |

本文规定仓库怎么放、环境怎么建、按什么顺序实现、怎样对照验收。行为以需求规格为准，技术落点以技术设计为准。

## 1. 环境

本机 Conda 安装在 `/opt/miniconda3`，版本 26.3.2。`base` 当前是 Python 3.13.13。系统 `python3` 是 Homebrew 的 Python 3.14.6。本项目两者都不用。

新建专用环境，名字是 `dylan`，Python 使用 Conda 能解析到的 3.12 系列，最低 3.12.0。不向 `base`、`agent`、`llmrl`、`choice`、`blender`、`ragepc`、`rlgame`、`roge`、`taiqiu`、`piroker` 安装本项目依赖。

`environment.yml`：

```yaml
name: dylan
channels:
  - conda-forge
dependencies:
  - python=3.12
  - pip
  - pip:
      - -r requirements.txt
      - -r requirements-dev.txt
```

`requirements.txt` 只写技术设计第 2.1 节的四个包和下限。`requirements-dev.txt` 只写 pytest 与 ruff 的下限。

首次安装：

```bash
conda env create -f environment.yml
conda activate dylan
python -m pip freeze > requirements.lock
```

以后重建使用 `conda env create -f environment.yml`，再按锁定文件安装。更换依赖时先改清单，再重新生成锁定文件。锁定文件入库。`.env` 不入库。

运行与测试前确认：

```bash
conda activate dylan
python -c "import sys; assert sys.version_info[:2] == (3, 12)"
```

## 2. 仓库结构

实现开始后，仓库根目录是下面这些条目。现在已经存在的只有三份文档；其余在对应里程碑创建，不预填空模块。

```text
.
├── REQUIREMENTS.md
├── TECHNICAL.md
├── DEVELOPMENT.md
├── environment.yml
├── requirements.txt
├── requirements-dev.txt
├── requirements.lock
├── pyproject.toml
├── .gitignore
├── .env.example
├── persona/
│   └── identity.md
├── data/                          # 忽略。运行后才有 dylan.db 与 dylan.db.lock
├── src/
│   └── dylan/
│       ├── __init__.py
│       ├── __main__.py            # python -m dylan
│       ├── clock.py
│       ├── config.py
│       ├── errors.py
│       ├── cli/
│       │   ├── main.py
│       │   └── commands.py
│       ├── llm/
│       │   ├── client.py
│       │   ├── fake.py
│       │   └── compress.py        # 可选模型压缩，默认不注入
│       ├── dialogue/
│       │   ├── loop.py
│       │   ├── depth.py
│       │   ├── thought.py
│       │   ├── prompt.py
│       │   ├── buffer.py
│       │   ├── extract.py
│       │   ├── rules.py
│       │   └── secrets.py
│       └── memory/
│           ├── constants.py
│           ├── model.py
│           ├── roles.py
│           ├── jaccard.py
│           ├── lexicon_zh.py
│           ├── schema.sql
│           ├── store.py
│           ├── encode.py
│           ├── anchors.py
│           ├── recall.py
│           ├── hebbian.py
│           ├── decay.py
│           ├── prune.py
│           ├── lifecycle.py
│           ├── stage.py
│           ├── compress.py
│           ├── health.py
│           └── consolidate/
│               ├── runner.py
│               ├── dedup.py
│               ├── merge.py
│               ├── enrich.py
│               ├── infer.py
│               ├── semantic_link.py
│               ├── habits.py
│               ├── summarize.py
│               ├── mature.py
│               ├── compress.py
│               ├── prune.py
│               └── dream.py
└── tests/
    ├── conftest.py
    ├── test_no_forbidden_deps.py
    ├── test_process.py            # 正常退出、Ctrl-C、文件锁、损坏库、缺库的开发命令
    ├── test_ac01.py … test_ac30.py
    └── support/
        ├── graph.py               # 仅 AC-07、AC-20 手造图
        └── clock.py
```

`pyproject.toml` 使用 src 布局。控制台入口：

```text
dylan = dylan.cli.main:main
```

`python -m dylan` 与命令 `dylan` 进入同一函数。

`.gitignore` 至少包含：`.env`、`data/`、`__pycache__/`、`.pytest_cache/`、`.ruff_cache/`、`*.db`、`*.db-wal`、`*.db-shm`。

`.env.example` 的键与技术设计第 8 节的表逐行相同，不得增删。密钥值为空，其余写该表中的默认值。

## 3. 模块职责

| 路径 | 职责 | 不负责 |
| --- | --- | --- |
| `clock.py` | `Clock` 协议、`SystemClock`、测试用的可拨动时钟 | 业务判断 |
| `config.py` | 读取环境变量并校验 | 打开数据库 |
| `errors.py` | 第 9 节技术设计中的错误类别 | 拼接含密钥的消息 |
| `cli/main.py` | 解析子命令、取得锁、组装依赖、返回进程码 | SQL 与激活公式 |
| `cli/commands.py` | status、health、decay、prune、consolidate、lifecycle、reset-identity | 对话循环 |
| `llm/client.py` | DeepSeek 流式对话、JSON 提取、错误分类 | 决定记忆类型 |
| `llm/fake.py` | 测试替身，回显思考记录 | 生产路径 |
| `dialogue/loop.py` | 需求第 5 节的一轮顺序和退出顺序 | 直接写 SQL |
| `dialogue/depth.py` | 四档深度 | 传播 |
| `dialogue/thought.py` | 思考记录数据结构 | 召回 |
| `dialogue/prompt.py` | 消息顺序、两套预算、禁止内部字段名的约束 | 调用网络 |
| `dialogue/buffer.py` | 最近 12 轮；溢出时请求收成情景 | 巩固策略 |
| `dialogue/rules.py` | 技术设计第 6.5 节的规则表 | 模型调用 |
| `dialogue/extract.py` | 规则结果加模型 JSON，再交给校验 | 扩散激活 |
| `dialogue/secrets.py` | 密钥形态扫描 | 通用敏感信息检测 |
| `memory/constants.py` | 需求表格和技术设计第 12 节的唯一字面量 | 业务分支 |
| `memory/model.py` | 神经元、突触、纤维、枚举、校验 | I/O |
| `memory/roles.py` | 角色、逆边、方向 | 传播循环 |
| `memory/jaccard.py` | 字符 bigram Jaccard | 分词 |
| `memory/lexicon_zh.py` | 时间同义闭集 | 开放域同义词 |
| `memory/schema.sql` | 版本 1 的表 | 数据 |
| `memory/store.py` | 连接、事务、迁移、CRUD、统计表 | 公式 |
| `memory/encode.py` | 复用神经元、去重、逆边成对、来源与信任截断 | 模型 |
| `memory/anchors.py` | 锚点与时间候选 | 传播 |
| `memory/recall.py` | 反射激活、共激活、因果修正、得分、态度、可见文本 | 打印回答 |
| `memory/hebbian.py` | `Δw = 0.05 × pre × post × (1 - w)` 与固定增量 | 选择突触 |
| `memory/decay.py` | 幂等衰减 | 删除 |
| `memory/prune.py` | 物理删除的条件 | 软删除入口 |
| `memory/lifecycle.py` | 钉住、冻结、解冻、恢复、软删除 | 对话检测 |
| `memory/stage.py` | `episodic` 到 `working` 的自动晋升 | `semantic` 晋升 |
| `memory/compress.py` | 抽取式摘要、要点、痕迹和层级进退 | 网络 |
| `memory/health.py` | 四项和建议的第一条 | 执行策略 |
| `memory/consolidate/runner.py` | 短巩固、`all`、单策略、预览回滚 | 各策略内部条件 |
| `persona/identity.md` | 人读、可改的种子 | 运行时状态 |

`memory/consolidate/mature.py` 执行 `working` 到 `semantic`。自动的 `episodic` 到 `working` 留在 `stage.py`，由召回事务调用。

## 4. 身份种子

`persona/identity.md` 使用中文，至少包含下面六句的意思。实现时把这六句写成连贯正文，不增加桌面宠物、视觉或工具能力。

- 他的名字是 dylan。
- 他用用户正在使用的语言回答。用户用中文时，他用中文。
- 他区分自己记得的、模糊的、推断的和不知道的。
- 他不知道的个人事实，说自己没有印象。
- 他没有身体，也不声称自己在用户桌面上走动或看见用户的屏幕。
- 他是一个会随相处积累记忆的对话者。

首次启动把全文编码为钉住的 `identity` 纤维。文件以后改动不会被自动读入。`dylan reset-identity --yes` 删除现有身份纤维，再按当前文件重写。没有 `--yes` 就拒绝执行。该命令不删除用户记忆。

## 5. 实现顺序

一个里程碑完成的标准，是它列出的测试通过，并且没有写该里程碑之外的行为。不保留「先能聊再补记忆」的中间产品；对话里程碑依赖前面的记忆里程碑。

| 里程碑 | 产出 | 必须通过 |
| --- | --- | --- |
| M0 | Conda 环境、打包配置、忽略规则、`.env.example`、配置加载、时钟、错误类别 | 版本断言；缺密钥的对话入口非零退出，且不创建数据库。覆盖 AC-01 |
| M1 | 模式版本 1、仓储、模型校验、身份种子写入 | 新建库有钉住身份；再次打开不重写身份；损坏文件拒绝并保留原文件。覆盖 AC-02 的数据库部分、AC-04 的持久化前提 |
| M2 | 幂等衰减、修剪、软删除、冻结、恢复、钉住 | AC-05、AC-21、AC-24、AC-26、AC-27。同一时钟连续衰减两次，强度不变 |
| M3 | 锚点、同义闭集、反射激活、共激活、因果角色、深度、可见文本 | AC-07、AC-08、AC-15、AC-16、AC-17、AC-18、AC-19、AC-20、AC-23 |
| M4 | 规则提取、校验、逆边、去重、假设置信、密钥扫描 | AC-03 的写入与再次召回、AC-09、AC-10、AC-30 |
| M5 | 会话缓冲、思考记录、提示组装、假模型对话循环、溢出收成情景 | AC-03、AC-08、AC-12。替身必须看见思考记录 |
| M6 | DeepSeek 客户端、流式中断、错误类别、请求体断言 | AC-11、AC-13。用假传输层，不访问网络 |
| M7 | 阶段晋升与全部巩固策略、健康建议、短巩固选择 | AC-06、AC-22、AC-25、AC-28、AC-29 |
| M8 | 压缩层级进退、热层独立预算、隐私固定句只打印一次 | AC-02、AC-19，以及预算超限时丢低分纤维 |
| M9 | 全部命令、数据库旁的文件锁、`Ctrl-C` 不跑短巩固、禁止依赖扫描 | AC-14、`test_process.py`、`test_no_forbidden_deps.py` |

每个里程碑结束时运行：

```bash
conda activate dylan
pytest
ruff check src tests
```

## 6. 编码约束

- 公共函数有参数和返回类型。
- 需求中的阈值、lambda、到期天数和乘数只出现在 `memory/constants.py`。
- `memory` 包的导入图不得到达 `openai`、`dialogue` 和 `cli`。由 `test_no_forbidden_deps.py` 扫描源码文本。
- 一次逻辑写入一个事务。召回后的加强、共激活统计和阶段晋升与该次召回提交在一起。
- 时间存 UTC，序列化形如 `2026-11-03T12:00:00Z`。比较前都转到这个钟的时刻。
- 标识在 Python 里是 `str`。
- 日志不写环境变量、请求头和用户原文中的令牌。
- 标准输出只有隐私说明和回答。开发命令的结果写到标准输出，因为它们不是对话。思考记录和警告写到标准错误。
- 不添加需求规格第 4.2 节排除的功能开关。排除项没有隐藏入口。

## 7. 测试

`tests/conftest.py` 为每个测试提供临时数据库、停在 `2026-11-03T00:00:00Z` 的可拨动时钟，以及假模型。假模型默认不要求密钥。

AC 与测试文件一一对应：`tests/test_ac01.py` 到 `tests/test_ac30.py`。一个验收里有两个断言时，放在同一文件的两个测试函数里，不拆到别的编号。

手造图只允许 `tests/support/graph.py` 被 `test_ac07.py` 和 `test_ac20.py` 导入。其余测试从对话或仓储的公开写入进入。

假传输层放在 `tests/support`，供 AC-11 与 AC-13 断言超时、中断和请求 JSON。它断言 `extra_body.thinking.type == "disabled"`，并且 `model == "deepseek-flash"`。

禁止依赖测试读取 `src/dylan`、`requirements.txt`、`requirements-dev.txt`、`environment.yml`，确认技术设计第 2.3 节的包名都没有出现。

## 8. 追溯

下表用来核对实现没有漏项。模块列是责任模块；测试列是验收文件。没有单独 AC 的需求行，测试列写实现约束对应的测试。

| 需求 | 责任模块 | 测试 |
| --- | --- | --- |
| FR-01 启动、空行、正常退出与短巩固 | `cli/main.py`、`dialogue/loop.py`、`consolidate/runner.py` | `test_ac01.py` 覆盖缺密钥；`test_process.py` 覆盖空行、`exit` 的短巩固顺序，以及 `Ctrl-C` 不巩固 |
| FR-02 一轮顺序 | `dialogue/loop.py` | `test_ac03.py` |
| FR-03 提示内容 | `dialogue/prompt.py` | `test_ac03.py`、`test_ac08.py` |
| FR-04 12 轮缓冲 | `dialogue/buffer.py` | `test_ac12.py` |
| FR-05 流式与中断 | `llm/client.py`、`dialogue/loop.py` | `test_ac11.py` |
| FR-06 不复述字段名 | `dialogue/prompt.py` | `test_ac03.py` 断言系统约束含此禁令 |
| FR-07 思考记录开关 | `config.py`、`dialogue/loop.py` | `test_ac03.py` 打开开关时标准错误含 `depth` |
| FR-10 首次种子 | `memory/encode.py`、`persona/identity.md` | `test_ac02.py` |
| FR-11 再次打开不重种 | `memory/store.py` | `test_ac04.py` |
| FR-12 第 9 节全部记忆行为 | `memory` 包 | AC-05 至 AC-07、AC-09、AC-15 至 AC-30 |
| FR-13 可注入时钟 | `clock.py` | AC-05、AC-06、AC-17、AC-19、AC-21、AC-26 |
| FR-14 原文保存 | `memory/encode.py` | `test_ac03.py` 断言库中的内容与用户原句一致 |
| FR-15 状态与健康 | `cli/commands.py`、`memory/health.py` | `test_ac29.py` |
| FR-16 软删除与恢复 | `memory/lifecycle.py`、`dialogue/rules.py` | `test_ac24.py` |
| FR-17 巩固命令与预览 | `consolidate/runner.py` | `test_ac22.py`、`test_ac25.py`、`test_ac28.py` |
| FR-18 生命周期命令 | `cli/commands.py`、`memory/lifecycle.py` | `test_ac27.py` |
| FR-20 默认模型可配置 | `config.py`、`llm/client.py` | `test_ac13.py` |
| FR-21 关闭思考模式 | `llm/client.py` | `test_ac13.py` |
| FR-22 缺密钥 | `cli/main.py` | `test_ac01.py` |
| FR-23 错误类别且不泄密 | `errors.py`、`llm/client.py` | `test_ac11.py` |
| FR-24 超时 60 秒 | `config.py` | `test_ac11.py` |
| FR-25 两套预算 | `dialogue/prompt.py` | M8 的预算测试放在 `test_ac19.py` |
| FR-30 示例环境与忽略规则 | 仓库根 `.env.example`、`.gitignore` | `test_no_forbidden_deps.py` 同时断言示例文件存在且密钥为空 |
| FR-31 密钥形态 | `dialogue/secrets.py` | `test_ac10.py` |
| FR-32 不读无关资源 | `memory/store.py`、`cli/main.py` | `test_ac14.py` 检查源码没有剪贴板、屏幕和前台窗口接口 |
| FR-33 出境范围与隐私句 | `llm/client.py`、`dialogue/loop.py` | `test_ac02.py`、`test_ac14.py` |
| D-01 自研记忆 | `memory` 包 | `test_no_forbidden_deps.py` |
| D-02 退路默认关闭 | 依赖清单 | `test_no_forbidden_deps.py` |
| D-03 命令行 | `cli/main.py` | M9 |
| D-04、D-05 模型与思考开关 | `llm/client.py` | `test_ac13.py` |
| D-06 单文件 SQLite | `memory/store.py` | `test_ac04.py` |
| D-07 单大脑 | `memory/schema.sql` | `test_ac02.py` |
| D-08 只读一个变量 | `config.py` | `test_ac01.py` |
| D-09 文本压缩 | `memory/compress.py` | `test_ac19.py` |
| D-10 做梦不是 clear | `consolidate/dream.py`、`memory/recall.py` | `test_ac25.py` |
| 第 9.2 节假设置信 | `memory/encode.py` | `test_ac30.py` |
| 第 9.4 节幂等 | `memory/decay.py` | M2 附加断言，放在 `test_ac05.py` |
| 第 9.6 节工作阶段 | `memory/stage.py` | `test_ac06.py` |
| 第 9.8 节短巩固只多跑一个策略 | `consolidate/runner.py` | `test_ac29.py` |
| 第 9.9 节建议顺序 | `memory/health.py` | `test_ac29.py` |

三十个 AC 都有同号测试文件。上表没有点名的 AC-15 至 AC-18、AC-20 至 AC-23、AC-26、AC-28 由第 5 节里程碑列到对应文件，责任模块分别是 `recall.py`、`depth.py`、`lifecycle.py`、`decay.py`、`consolidate/habits.py`。

## 9. 完成定义

第 0 阶段实现完成，当且仅当：

1. `conda activate dylan` 后 `pytest` 全部通过，且测试进程没有对外网络连接。
2. `ruff check src tests` 通过。
3. `test_no_forbidden_deps.py` 通过。
4. 追溯表中每一行的责任模块存在，并且被对应测试导入或经命令间接执行。
5. 需求规格第 4.2 节的排除项在源码和依赖清单中都没有入口。

真实 DeepSeek 的手动对话不作为完成条件。需要手动看回答语气时，在已激活的 `dylan` 环境中设置 `DEEPSEEK_API_KEY` 后执行 `dylan`。

## 10. 修订

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| 0.1 | 2026-11-03 | 首版 |
| 0.2 | 2026-11-03 | 对齐需求规格 0.3 与技术设计 0.2 |
