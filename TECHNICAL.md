# dylan 技术设计说明

| 项 | 内容 |
| --- | --- |
| 文档编号 | DYLAN-TDD-001 |
| 版本 | 0.2 |
| 状态 | 与需求规格 0.3 对齐，供实现使用 |
| 日期 | 2026-11-03 |
| 上位文档 | [REQUIREMENTS.md](REQUIREMENTS.md)（DYLAN-SRS-001，0.2） |
| 配套文档 | [DEVELOPMENT.md](DEVELOPMENT.md) |
| 读者 | 实现者 |

需求规格规定行为。本文规定技术落点。二者冲突时以需求规格为准，并先改需求规格再改代码。本文出现的公式、阈值、类型名和命令语义与需求规格第 6、9、11 节一致；需求规格没有给出、但实现必须唯一的数值，集中在第 12 节，称为实现参数。

## 1. 技术决策

本阶段是单机、单进程、单用户的命令行程序。记忆算法和持久化都在本仓库内完成。默认不安装、不导入 `neural-memory`。

| 编号 | 决策 | 选择 | 原因 |
| --- | --- | --- | --- |
| TD-01 | 语言与运行时 | Python 3.12，由 Conda 环境 `dylan` 提供 | 记忆算法、SQLite 和测试都用同一语言。3.12 在本机 Conda 可安装。不使用系统自带的 Python 3.14，也不往 `base`、`agent`、`llmrl` 等已有环境里装依赖 |
| TD-02 | 环境定义 | 仓库内 `environment.yml` | 环境可复现。安装步骤见开发文档 |
| TD-03 | 依赖面 | 见第 2 节。记忆算法只用标准库 | 需求禁止向量库和嵌入模型。少一个依赖，就少一条把召回做成近邻搜索的路径 |
| TD-04 | 图存储 | 标准库 `sqlite3`，单文件 `data/dylan.db` | 对应决策 D-06。一个连接、串行事务。不用 ORM，不用图数据库 |
| TD-05 | 图遍历 | 本进程内的 Python 对象 | 反射激活是有界跳数的通路传播，不是数据库里的向量查询 |
| TD-06 | 模型接入 | 官方 `openai` SDK，`base_url=https://api.deepseek.com` | 接口与 OpenAI Chat Completions 兼容，对应 D-04。流式回答和非流式提取、压缩都走这个客户端 |
| TD-07 | 配置对象 | `pydantic-settings` | 第 11 节的配置项需要类型和默认值。缺密钥时在进入对话前失败 |
| TD-08 | 本地密钥文件 | `python-dotenv` 只在进程启动时把仓库根目录的 `.env` 填入环境变量 | 已存在的环境变量优先。密钥仍只从 `DEEPSEEK_API_KEY` 读取 |
| TD-09 | 命令行 | 标准库 `argparse` | 交互面只有一组子命令。不引入 TUI 或 Web 框架 |
| TD-10 | 时间 | 可注入的 `Clock`。生产用 UTC 系统钟，测试用 `FakeClock` | 对应 FR-13。衰减、到期、阶段、压缩和习惯日期都读这一个钟 |
| TD-11 | 标识 | 标准库 `uuid.uuid4` 的字符串 | 神经元、突触、纤维和一次召回的编号 |
| TD-12 | 架构风格 | 同步调用 | 单连接 SQLite 与同步流式输出一致。不使用 `asyncio`，避免第二个线程写库 |
| TD-13 | 压缩正文的默认算法 | 抽取式规则 | 需求允许规则或一次模型调用。默认规则使巩固和验收不依赖网络。模型压缩是关闭的开关 |
| TD-14 | 中文关联 | 字符 bigram，加一份可审查的同义闭集 | 需求禁止嵌入。验收句「晚上」要能走到「深夜」，必须有显式同义边。闭集不是向量模型 |
| TD-15 | D-02 退路 | 默认依赖清单不包含 `neural-memory` | 只有中文锚点验收失败、并且闭集与 bigram 都补过之后，才单独立项评估。评估前不安装 |

## 2. 依赖

### 2.1 运行依赖

| 包 | 下限 | 用途 |
| --- | --- | --- |
| `openai` | 1.40 | DeepSeek 的 Chat Completions 与流式响应 |
| `pydantic` | 2.7 | 记忆对象、思考记录、提取结果的校验 |
| `pydantic-settings` | 2.4 | 环境变量配置 |
| `python-dotenv` | 1.0 | 启动时加载 `.env` |

安装时取满足下限的当前稳定版。第一次安装成功后，由开发文档中的命令生成 `requirements.lock`。本文不手写一份未安装过的锁定版本。

### 2.2 开发依赖

| 包 | 下限 | 用途 |
| --- | --- | --- |
| `pytest` | 8.0 | 验收测试 |
| `ruff` | 0.6 | 导入边界和基本静态检查 |

### 2.3 明确不安装

下列包不得出现在 `environment.yml`、`requirements.txt` 或锁定文件中：

- `neural-memory`
- `chromadb`、`faiss-cpu`、`faiss-gpu`、`qdrant-client`、`pymilvus`、`lancedb`、`pgvector`
- `sentence-transformers`、`FlagEmbedding`、以及任何嵌入模型包
- `numpy`、`scipy`、`networkx`、`torch`
- `jieba`、`pkuseg`、`spacy`
- `fastapi`、`flask`、`uvicorn`、`gradio`、`streamlit`
- `PySide6`、`PyQt6`、`textual`、`rich`

记忆计算使用标准库 `math`。中文切分使用字符 bigram，不使用分词器。

## 3. 运行时结构

```text
命令行 argparse
    → 应用启动（配置、锁、开库、补记衰减、种子身份）
        → 对话循环 或 开发命令
            → 记忆服务（纯算法，不导入 openai）
                → SQLite 仓储（唯一的写入口）
            → 模型端口（对话、提取、可选压缩）
```

依赖方向只允许向下：

| 模块 | 可以导入 | 禁止导入 |
| --- | --- | --- |
| `dylan.memory` | 标准库、`pydantic`、`dylan.clock` | `openai`、`dylan.llm`、`dylan.dialogue`、`dylan.cli` |
| `dylan.llm` | `openai`、配置、错误类型 | `dylan.memory` 的仓储、`dylan.cli` |
| `dylan.dialogue` | `dylan.memory` 的服务接口、`dylan.llm` 的端口、`dylan.clock` | `sqlite3` |
| `dylan.cli` | 上述三者的组装入口 | 在命令层里写 SQL 或激活公式 |

`memory` 需要正文压缩时，只依赖自己定义的 `TextCompressor` 协议。默认实现是抽取器，放在 `dylan.memory.compress`。可选的模型实现放在 `dylan.llm`，由启动代码注入。

## 4. 进程生命周期

单进程持有一把文件锁，使用 `fcntl.flock`。锁文件与数据库同目录，文件名是数据库文件名加 `.lock`。默认数据库 `data/dylan.db` 的锁是 `data/dylan.db.lock`。锁已被占用时，进程以非零状态退出，说明已有一个 dylan 在使用这块大脑。锁是实现手段，用来保证需求中的单连接串行写入。

启动顺序：

1. 加载 `.env`，再读取环境变量。已有环境变量不被 `.env` 覆盖。
2. 校验配置。对话命令缺少 `DEEPSEEK_API_KEY` 时，按 FR-22 退出，并且不创建数据库文件。`status`、`health`、`decay`、`prune`、`consolidate`、`lifecycle`、`reset-identity` 不读取密钥，也不创建客户端。这些命令在数据库文件不存在时不创建文件，以非零状态退出并说明记忆库不存在。
3. 取得文件锁。
4. 打开 SQLite。文件不存在：建库、写入大脑行 `dylan`、写入钉住身份，并打印隐私说明。文件存在：只打开，不重新写入身份。文件存在但不是合法库、模式版本更高、或大脑名不是 `dylan`：打印错误类别并退出，不删除文件，不重建身份。
5. 模式合法但钉住身份纤维不存在：打印错误，提示只能通过 `reset-identity` 恢复，不自动补种。
6. 用时钟计算自各行 `decay_cursor` 以来的时间，幂等地补记衰减。
7. 进入对话或执行开发命令。

一轮对话的事务边界：

1. 召回、思考记录、流式回答在模型返回完成之前不写长期记忆。
2. 回答完整结束后，提取与赫布更新放在同一个事务里提交。
3. 流中断：保留已打印文本，提示本轮不完整，该轮不做提取，不把半截回答写成事实。
4. 提取事务失败：回答已经显示，事务回滚。下一轮开始前先打印「上一轮没有记住」。警告文案不得包含被拦截的令牌。

退出：

| 方式 | 行为 |
| --- | --- |
| `exit`、`quit`、EOF | 先把本次会话收成一条 `episode` 并提交，再执行短巩固，然后关闭连接并解锁 |
| `Ctrl-C`、被信号杀死 | 视为异常退出。已提交的事务保留。不写会话情景，不跑短巩固 |
| 写库过程中崩溃 | 只丢失未提交事务 |

短巩固的顺序固定为 `dedup`、`prune`、`mature`。然后取健康建议里第一个属于下列集合的策略，最多再跑一个：`learn_habits`、`infer`、`compress`、`merge`、`summarize`、`semantic_link`、`enrich`。健康建议若先命中 `prune`、`mature` 或「先处理冲突」，不再额外运行策略。冲突不自动改写，只留待下一次相关召回进入思考记录。`DYLAN_AUTO_DREAM=false` 时到此结束。该值为 `true` 时，最后再运行一次 `dream`。默认是 `false`。

## 5. 持久化

### 5.1 SQLite 设置

- 一个进程一个连接，`check_same_thread=True`。
- `PRAGMA foreign_keys=ON`
- `PRAGMA journal_mode=WAL`
- `PRAGMA synchronous=NORMAL`
- `PRAGMA busy_timeout=5000`
- 连接的 `row_factory` 为 `sqlite3.Row`。

WAL 的 `-wal` 与 `-shm` 文件位于 `data/`，随目录一起被忽略。正常关闭时执行 `PRAGMA wal_checkpoint(TRUNCATE)`。

### 5.2 模式版本

表 `meta` 保存：

| 列 | 含义 |
| --- | --- |
| `schema_version` | 整数。当前版本为 `1` |
| `brain_name` | 固定 `dylan` |
| `created_at` | 建库时间 |
| `privacy_notice_shown` | 首次隐私说明是否已经打印 |
| `last_decay_at` | 最近一次衰减作业的时间 |

版本等于代码版本则直接打开。版本更低则在一个事务里按序迁移。版本更高则拒绝打开。任何迁移失败都回滚并退出。

### 5.3 表

只保存需求中的对象，外加算法无法幂等完成时所必需的游标和统计。不另建项目表、用户表或快照表。

`neurons`

| 列 | 约束 |
| --- | --- |
| `id` | 主键 |
| `kind` | `entity`、`concept`、`episode`、`time`、`emotion` |
| `content` | 原文，非空 |
| `content_key` | `kind` 与规范化内容的唯一键。规范化只去掉首尾空白；含拉丁字母时对拉丁字母做 casefold，中文保持原样 |
| `pinned` | 0 或 1 |
| `state` | `active`、`frozen`、`soft_deleted` |
| `created_at` | UTC ISO-8601，带 `Z` |
| `deleted_at` | 软删除时间，可空 |

同一 `kind + content_key` 只允许一个神经元。写入时先查找再创建。时间神经元的 `content` 使用半开区间的规范串 `YYYY-MM-DD/YYYY-MM-DD`，单日的结束日期为下一天。

`synapses`

| 列 | 约束 |
| --- | --- |
| `id` | 主键 |
| `source_id`，`target_id` | 外键，指向神经元，两者不得相同 |
| `type` | 第 6.1 节的类型之一 |
| `direction` | `uni` 或 `bi` |
| `base_weight` | 未经时间曲线折算的重量，范围 `[0,1]` |
| `weight` | 折算后的有效重量，范围 `[0,1]` |
| `rehearsal_count` | 非负整数 |
| `last_activated_at` | 可空 |
| `decay_cursor` | 衰减已经结算到的时间 |
| `created_at` | 非空 |

唯一键：`(source_id, target_id, type)`。

`fibers`

保存需求第 9.1 节的纤维字段。另加实现列：`base_conductivity`、`decay_cursor`、`deleted_at`、`body`。`body` 是层级 0 到 3 的原文；层级 4 时置空。`summary`、`essence`、`ghost` 分列存放。`essence` 最长 150 个码位。`provenance` 存 JSON，字段只有 `source`、`confidence`、`trust`。`recall_dates` 存去重后的 `YYYY-MM-DD` JSON 数组，供阶段晋升使用。`confidence_value` 保存假设的数值置信，非假设为空。

`fiber_neurons(fiber_id, position, neuron_id)` 保存有序通路。`position` 从 0 开始，`position=0` 的神经元必须等于 `anchor_neuron_id`。

`fiber_synapses(fiber_id, synapse_id)` 保存纤维包含的突触。

`fiber_tags(fiber_id, tag)` 保存 `auto_tags`。标签在写入前去掉首尾空白并转为小写拉丁字母；中文标签保持原样。

`coactivations(neuron_a, neuron_b, count, last_on)`

`neuron_a < neuron_b`，按标识的字典序。一次召回里由两个及以上锚点共同激活的神经元对，在召回事务中把 `count` 加一。`infer` 读取 `count ≥ 2` 且尚无侧向突触的对。

`sequence_observations(signature, day)`

`signature` 是有序概念神经元标识用 `>` 连接的串。唯一键为 `(signature, day)`。同一顺序在不同日期出现不少于 3 次时，`learn_habits` 可以收成 `workflow`。

`recall_runs(run_id, created_at)` 与 `recall_hits(run_id, neuron_id)`

每次实际召回写一行运行和它命中的概念神经元。`dream` 只读这些表：两团概念在不同 `run_id` 中交替出现，且当前图上没有通路。

这些统计表不参与提示词，不作为可以对自己说出的记忆。

### 5.4 衰减幂等

需求给出的是一次结算公式。若每次启动都用「自 `last_activated_at` 起的全部时长」再乘一次当前强度，同一段时间会被重复衰减。实现改为结算增量，结果与公式在「只结算一次」时相同。

纤维：

```text
delta_days = max(0, now - decay_cursor) 换算成日，保留小数
factor = exp(-lambda_effective × tier_multiplier × delta_days / stability)
conductivity = max(floor, conductivity × factor)
decay_cursor = now
```

`lambda_effective` 取该记忆类型的每日 lambda。语义阶段再乘 `0.25`。`tier_multiplier` 热层 `0.5`、温层 `1`、冷层 `2`。地板取适用下限的最大值：热层 `0.5`，语义阶段 `0.8`。`identity`、`pinned=1`、`state=frozen` 不乘因子，只把 `decay_cursor` 拨到 `now`，因此冻结或钉住的时段不补扣。

突触不保存一条会重复相乘的有效重量。每次需要读重量时：

```text
h = max(0, now - last_activated_at) 的小时数；last_activated_at 为空则用 created_at
half_life = 1440 × (1 + 0.5 × rehearsal_count)
spread = half_life / 2
factor = 1 / (1 + exp((h - half_life) / spread))
floor = 0.3 + min(0.5, 0.05 × rehearsal_count)
weight = base_weight × max(floor, factor)
```

赫布更新修改 `base_weight`，然后按上式重算 `weight`，并把 `last_activated_at` 与 `decay_cursor` 设为 `now`。同一时钟下重复调用衰减，`base_weight` 不变，有效重量不变。

`stability = 1 + ln(1 + rehearsal_count)`，`rehearsal_count` 为 0 时稳定性为 1。

### 5.5 到期与软删除

到期日到达时，把纤维 `state` 设为 `soft_deleted`，`deleted_at` 设为 `expires_at`。之后它遵守同一套宽限和恢复规则。宽限默认 7 天，从 `deleted_at` 算起。修剪只物理删除宽限已满的软删除对象，以及同时满足「有效重量低于 `0.05`」和「`last_activated_at` 早于 7 天」的突触。

物理删除纤维时，删除其关联行。物理删除突触后，删除不再被任何突触或纤维引用、且未钉住的神经元。

身份、`boundary` 和 `pinned=1` 的纤维拒绝对话中的软删除。命令层返回明确原因，不修改行。

冻结只改 `state`。解冻改回 `active`。恢复只接受宽限期内的 `soft_deleted`，把 `state` 改回 `active` 并清空 `deleted_at`。已物理删除的对象不能恢复。

钉住时同时写 `pinned=1` 和 `tier='hot'`。

## 6. 记忆算法落点

### 6.1 突触类型与角色

类型闭集与需求第 9.1 节相同。写入校验拒绝闭集之外的类型。需求第 4.2 节排除、校验器必须拒绝的灌库类型是：`imports`、`calls`、`depends_on`、`inherits`、`implements`、`defined_in`、`raises`、`has_value`、`measured_at`、`regulates`、`in_row`、`in_column`。

| 角色 | 类型 | 召回后处理 |
| --- | --- | --- |
| 被动 | `happened_at`、`during`、`alias`、`stored_by`、`verified_at`、`approved_by` | 不传播。`happened_at` 只在时间锚点检索时使用 |
| 深度 3 才传播 | `felt`、`evokes` | 深度小于 3 时当作被动 |
| 顺序 | `before`、`after`、`caused_by`、`leads_to`、`enables` | 源端已激活时向下一跳追加激活，跳数仍受深度上限约束 |
| 削弱 | `prevents`、`contradicts`、`evidence_against` | 目标激活乘 `0.7`。`contradicts` 与其他削弱关系命中的纤维对写入 `conflicts` |
| 加强 | `evidence_for`、`verified_by`、`effective_for` | 目标激活乘 `1.1`，上限 `1` |
| 替代 | `supersedes`、`evolves_from` | 提高源端、压低目标端，乘数分别为 `1.1` 与 `0.7`，上限 `1` |
| 替代 | `resolved_by`、`falsified_by` | 提高目标端、压低源端，乘数同上 |
| 侧向 | `co_occurs`、`related_to`、`similar_to`、`near`、`used_with` | 按反射公式传播，方向为双向 |
| 结构 | `is_a`、`has_property`、`involves`、`at_location`、`contains`、`source_of`、`predicted`、`derived_from`、`subgoal_of` | 按反射公式单向传播 |

逆边成对写入，缺一不可：`before` 与 `after`，`caused_by` 与 `leads_to`，`contains` 与 `at_location`。双向类型只保存一行，遍历时两端都可走。

默认重量 `0.5`。同义闭集写出的 `similar_to` 使用第 12 节的重量。`infer` 写出的 `related_to` 重量为 `0.3`，来源为 `consolidation`。

### 6.2 记忆类型参数

记忆类型闭集只有：`identity`、`boundary`、`fact`、`preference`、`decision`、`instruction`、`insight`、`hypothesis`、`schema`、`reference`、`tool`、`context`、`workflow`、`prediction`、`error`、`todo`、`episode`。每日 lambda、默认到期和默认层级与需求第 9.1 节的表一致，集中定义在 `dylan.memory.constants`。闭集之外的提取项丢弃，并记入本轮写入警告。`identity` 不衰减、不到期、写入时钉住并置于热层。`boundary` 的 lambda 为 `0.01`，默认热层且钉住。`instruction` 的 lambda 为 `0.05`，默认热层，不默认钉住。

优先级默认 `5`。身份和边界默认 `10`。

来源信任上限：`user_input` 为 `0.9`，`ai_inference` 与 `consolidation` 为 `0.7`，`dream` 为 `0.5`。超过上限的值在入库前截断。`ai_inference` 的置信最高写到 `medium`。`dream` 的置信固定 `inferred`。

假设置信初值 `0.5`。支持证据：`c = c + 0.1 × (1 - c)`。反对证据：`c = c × 0.8`。结果写回该假设纤维的 `confidence_value`。

### 6.3 召回

深度判断按下列顺序，命中即停止。比较使用用户原句，不翻译。

| 顺序 | 条件 | 深度 | 最大跳数 | 时间窗 |
| --- | --- | --- | --- | --- |
| 1 | 含「为什么」「后来」「原因」「感受」「当时什么感受」之一 | 3 | 6 | 365 日 |
| 2 | 含「通常」「每次」「习惯」之一 | 2 | 4 | 30 日 |
| 3 | 含「我叫什么」「你是谁」「你叫什么」「我是谁」之一 | 0 | 0 | 不使用 |
| 4 | 其余 | 1 | 2 | 7 日 |

深度 2 在得分相同的候选里，把 `workflow` 和含 `before` 或 `after` 的纤维排在前面。这个排序不提高它们的分数上限。

锚点：

1. 从问句中的日期表达和同义闭集找到时间神经元。能对上的时间锚点初始激活为 `1.0`，并且是第一个锚点。
2. 实体锚点 `0.8`，动作或 `workflow` 锚点 `0.6`，概念锚点 `0.4`。
3. 神经元内容长度不少于 2，且问句完整包含该内容时，该锚点取本档上限。反向的「神经元包含问句里的某个片段」不单独升档，只走下一步的 Jaccard。
4. 否则用字符 bigram Jaccard。达到第 12 节阈值才成为锚点，初始激活为「本档上限 × Jaccard」。
5. 问句含时间范围时，把 `time_start` 到 `time_end` 与该范围相交的未排除纤维加入候选。
6. 问句含「我叫什么」或「我是谁」时，把已经记下的、来源为 `user_input` 的姓名事实里的 `entity` 当作实体锚点，初始激活 `0.8`。深度仍按上表，不因为这次查找而增加跳数。「你是谁」「你叫什么」不走这次查找。

没有锚点且没有时间候选时，召回为空，`certainty=none`。上一项的姓名锚点算锚点。会话缓冲单独附在提示中，并标明「刚才的对话」。

传播：

```text
activation(next) = current × (1 - decay_rate) × synapse.weight × fiber.conductivity × time_factor
```

`decay_rate` 默认 `0.2`。两端都有时间时，`time_factor = exp(-|Δ天| / 时间窗)`；否则为 `1`。激活低于 `0.2` 不再向外传播。

同一神经元收到 `n ≥ 2` 个锚点的激活时，激活改为 `min(1, 原激活 + 0.1 × n)`。召回提交时，只对共同激活了该神经元的那些锚点两两做赫布更新；两端激活已知时 `Δw = 0.05 × pre × post × (1 - w)`，作用在 `base_weight` 上。没有 `co_occurs` 就创建一条。

纤维得分：

```text
score = conductivity × mean(命中神经元激活) × stage_factor × priority_factor
priority_factor = 0.5 + priority / 20
```

`stage_factor`：`episodic` 为 `1`，`working` 为 `1.1`，`semantic` 为 `1.25`。平均的分母只计该纤维上激活不低于 `0.2` 的神经元。未激活成员不按 0 计入，避免长通路把单点命中稀释到阈值以下。没有命中神经元的纤维不得分。不参与得分的纤维：`soft_deleted`、`frozen`、已到期、以及本次没有被问句点名的冷层纤维。点名指问句与该纤维锚点内容的 Jaccard 达到锚点阈值，或用户原句含「更早」「以前」「老的」。

取得分不低于 `0.2` 的前 5 条。没有入选纤维时使用第 1 行。否则每条从第 2 行起归类，命中即停止。身份种子的来源写为 `user_input`，置信写为 `verified`。

| 顺序 | 条件 | certainty |
| --- | --- | --- |
| 1 | 没有纤维入选 | `none` |
| 2 | 来源是 `dream`、`consolidation` 或 `ai_inference`，或置信是 `low` 或 `inferred` | `inferred` |
| 3 | 得分不低于 `0.6`，且来源是 `user_input` 或该纤维是钉住身份 | `clear` |
| 4 | 得分不低于 `0.2` | `faint` |

被选中的纤维：`conductivity = min(1, conductivity + 0.02)`，`base_conductivity` 同步增加 `0.02`，`frequency` 加一，`last_conducted_at=now`，并把当天写入 `recall_dates`。若阶段为 `episodic`，且不同日期不少于 3、`frequency ≥ 3`，同一事务内升为 `working`。被传播经过的突触做赫布更新。

可见文本在组装提示前决定，不改库。年龄形式和层级形式分开计算，再取更短的一种。从长到短依次是：全文、摘要、要点、痕迹、仅元数据。

年龄形式：小于 7 日为全文；7 日及以上且小于 30 日为摘要；30 日及以上且小于 180 日为要点；180 日及以上为痕迹。层级形式：0 全文，1 摘要，2 要点，3 痕迹，4 仅元数据。所选档位没有正文时，向更长的一侧退一档，直到有内容。第 4 层不退回正文，只送类型、时间和标签。40 日且层级为 2 的纤维因此送要点，这是 AC-19 的路径。

热层中的 `identity`、`boundary`、`instruction` 始终送 `body`，走独立预算，不参与上面的缩短。普通召回预算 1500 个码位，热层预算 800 个码位。预算按得分从高到低装入，装不下的整条略去。热层按身份、边界、指令的顺序装入；某一条本身超过剩余预算时，截断到剩余码位。码位使用 Python 的 `len`。

### 6.4 写入与提取

每轮完整回答之后做两次确定，再进入一个事务：

1. 规则提取器处理用户原句。它负责需求里必须尝试写入的类型，规则见第 6.5 节。
2. 同一次非流式模型调用产出 JSON 候选，补规则没有覆盖的关系。`thinking.type` 为 `disabled`。模型失败或 JSON 不合法时，保留规则结果，并在下一轮前提示这一轮只记住了规则能确定的部分；若规则结果也为空，则提示这一轮没有记住。合法 JSON 只有这个形状：`{"items":[{"memory_type":"preference","summary":"原文中的短句","neurons":[{"kind":"time","content":"深夜"}],"links":[{"source":"深夜","target":"写代码","type":"related_to"}]}]}`。`items` 可为空数组。校验器按闭集过滤 `memory_type`、`kind` 和 `type`。
3. 校验器丢弃未知类型、排除类型、含密钥形态的文本，以及置信与信任越界的值。
4. 按 `kind + content_key` 复用神经元。摘要 bigram Jaccard 达到 `0.8` 的纤维不新建，导电度和 `base_conductivity` 各加 `0.05`，`rehearsal_count` 与 `frequency` 都加一，并把当天记入 `recall_dates`。复述也计入 `frequency`，否则只被重复说起、尚未被召回的纤维无法进入 `working`。
5. 会话缓冲超过 12 轮时，先用抽取器把最早一轮收成 `episode` 并提交，再从缓冲移除。这个收束不调用模型。

正常退出时的会话级 `episode` 同样用抽取器，连接本会话已经点中的概念和时间。

`ai_inference` 只用于模型候选里用户没有直说的认识。用户原句命中的规则项一律是 `user_input`。

### 6.5 规则提取

规则按表从上到下命中。一条句子可以同时命中关系和类型。

| 原句模式 | 结果 |
| --- | --- |
| 「忘掉」「忘记我说过」「别记」加一个内容片段 | 对未钉住纤维做软删除，不新建记忆 |
| 「我叫」「我是」后的人名 | `entity`，以及一条 `fact` |
| 「喜欢」「偏好」「讨厌」「不喜欢」 | `preference` |
| 「决定」「改成」「不用……了」 | `decision`。出现「改成」「不用……了」时，对新旧决定写 `evolves_from` |
| 「以后」「回答我时」「记得用」 | `instruction` |
| 「不可以」「别再」「不允许」 | `boundary`，并钉住 |
| 「待办」「记着要」「提醒我还有」 | `todo`。只存储，不调度 |
| 「报错」「失败了」「出错」 | `error` |
| 「流程是」「每次都是先」 | `workflow`，并写 `before` |
| 「因为」「所以」 | `caused_by` 与 `leads_to` |
| 「之前」「之后」「然后」 | `before` 与 `after` |
| 「在」加地点 | `at_location` |
| 「高兴」「难过」「生气」等情绪词 | `emotion` 与 `felt` |
| 「说错了」「不是这样」 | `contradicts` 或 `supersedes`，新旧事实都保留 |
| 同一轮里的两个人或两个概念 | `co_occurs` |
| 其余含实质内容的陈述 | `fact` 或 `episode` |

寒暄表为闭集：「你好」「在吗」「谢谢」「好的」「嗯」。只含寒暄时不写长期记忆。

标点（，。！？；等）只用来把一句分成若干截，再决定每一截留不留。寒暄和问句那一截不写，确认式问句（「是不是」「……吗」）也不写。其余截里，因果、先后、改口和更正合成一条纤维，摘要是这些截拼起来的内容；彼此独立的事实各写一条，并在同一轮之间写 `co_occurs`。模型交回的摘要若仍带着寒暄或问句，整条丢掉。

同义闭集写在 `dylan/memory/lexicon_zh.py`。闭集里的表面形式一律建成 `time` 神经元，不另建同文概念神经元。每组两两写双向 `similar_to`，重量见第 12 节。时间神经元作为锚点时初始激活为 `1.0`。按默认重量 `0.6`、`decay_rate=0.2`、导电度 `1` 计算，`晚上` 到 `深夜` 的激活为 `1.0 × 0.8 × 0.6 = 0.48`，高于 `0.2`，因此深度 1 可以给所在纤维记分。

| 组 | 表面形式 |
| --- | --- |
| 夜间 | 深夜、晚上、夜里、夜间、半夜 |
| 早晨 | 早上、早晨、上午 |
| 午后 | 下午、午后 |

「我喜欢深夜写代码」因此得到偏好纤维，通路含时间神经元「深夜」。「我晚上适合做什么」的锚点「晚上」经一条 `similar_to` 到达「深夜」，该纤维可以入选。这是 AC-03 的实现路径。闭集可以加词，不得改成统计嵌入。

### 6.6 巩固

各策略的候选条件和需求第 9.7、9.8 节一致。

| 策略 | 读什么 | 写什么 |
| --- | --- | --- |
| `dedup` | 摘要 bigram Jaccard ≥ `0.8` | 保留导电度较高的纤维，复述次数相加，另一条软删除 |
| `merge` | 神经元集合 Jaccard ≥ `0.5` | 合并有序通路和突触集合 |
| `enrich` | 缺标签、时间或类型、且原文里能直接抽出 | 只补能从原文截取的字段 |
| `infer` | `coactivations.count ≥ 2` 且无侧向突触 | 重量 `0.3` 的 `related_to`，来源 `consolidation` |
| `semantic_link` | 无公共神经元，标签 bigram Jaccard ≥ `0.5` | 锚点之间的 `similar_to`，来源 `consolidation` |
| `learn_habits` | 同一 `signature` 的不同日期 ≥ 3 | 一条 `workflow`，并加强沿途 `before` 与 `after` |
| `summarize` | 至少 3 条 `episode` 的非空 `auto_tags` 完全相同 | 一个 `concept` 神经元，一条 `insight` 纤维，来源 `consolidation` |
| `mature` | `working`，存在 ≥ 7 日，`frequency ≥ 5`，导电度 ≥ `0.6` | 阶段改为 `semantic` |
| `compress` | 按第 6.7 节 | 只降低层级 |
| `prune` | 第 5.5 节 | 物理删除 |
| `dream` | 见下段 | 一条桥接纤维，来源 `dream`，置信 `inferred` |

两个概念神经元 `a` 与 `b` 构成一对做梦候选，当且仅当：沿非被动突触、跳数不超过 6 时两者互不可达；至少两个召回运行命中 `a` 且未命中 `b`；至少两个召回运行命中 `b` 且未命中 `a`。桥接纤维的通路是 `[a, b]`，突触类型为 `related_to`，来源 `dream`。一次 `dream` 最多新建 3 条，按两端被命中次数之和从高到低选取。

`all` 的顺序：`dedup`、`merge`、`enrich`、`infer`、`semantic_link`、`learn_habits`、`summarize`、`mature`、`compress`、`prune`。`dream` 不包含在 `all` 里。`--dry-run` 计算候选并打印数量，事务回滚。

在线习惯不写 `workflow`。同一会话中，同一对有序概念若在两个轮次里以相同顺序出现，当即加强对应的 `before` 与 `after`。

### 6.7 压缩

抽取器：

- 摘要：原文按句号、问号、叹号切开后的前两句，最长 300 码位。
- 要点：摘要的第一句，最长 150 码位。
- 痕迹：要点的前 40 码位。

自动降级每次只降一档，且不得进入第 4 档。第 4 档仅当显式运行 `compress`、当前已是第 3 档、导电度低于 `0.2`、且 `last_conducted_at` 早于 180 日。被召回一次，层级向 0 回升一档；正文已经置空时不能回升出第 4 档。

`DYLAN_COMPRESS_WITH_MODEL=false` 为默认。设为 `true` 时，压缩调用与对话调用使用同一模型和 `thinking.type=disabled`。调用失败保持原层级，当轮回答仍使用退回规则。

### 6.8 健康

四项定义与需求第 9.9 节相同。成熟比例的分母是非 `identity` 纤维数；分母为 0 时比例为 0。连通是全部神经元的突触度平均值；没有神经元时为 0。新鲜是 `last_conducted_at` 落在最近 30 日的纤维比例。一条 `contradicts` 算作未处理，当它两端的神经元之间还不存在 `resolved_by` 或 `supersedes`。冲突数是这样的突触条数。

建议按需求顺序取第一条。输出五项：四项数值、一条建议名称。建议名称使用策略名，或固定句子「先处理冲突」「无需巩固」。

## 7. 对话与模型契约

### 7.1 客户端

```text
OpenAI(
  api_key=环境变量 DEEPSEEK_API_KEY,
  base_url=配置的 DEEPSEEK_BASE_URL,
  timeout=配置的超时秒数,
)
```

对话请求：

| 字段 | 值 |
| --- | --- |
| `model` | `DEEPSEEK_MODEL`，默认 `deepseek-flash` |
| `stream` | `true` |
| `extra_body.thinking.type` | `disabled` |
| `messages` | 第 7.2 节 |

不设置会把正常结束误判成中断的 `max_tokens`。只有底层流抛出异常时，才把本轮标为不完整。

提取请求：`stream=false`，同一模型，同一思考开关，`response_format={"type":"json_object"}`。解析失败则丢弃模型候选。

错误映射只保留类别：缺少密钥、认证失败、超时、服务错误、网络中断、记忆库损坏、写入失败。日志和提示不包含密钥、`Authorization` 头、令牌原文和完整请求体。

### 7.2 提示组成

消息顺序：

1. `system`：种子身份全文，加上回答约束。约束要求遵守思考记录里的态度，推断必须说是推断，没有印象就说没有印象，冲突要同时承认两边，可见回答不使用内部字段名。
2. `system`：热层身份、边界、指令的全文，预算 800。
3. `system`：思考记录的 JSON，以及压缩后的召回结果，预算 1500。
4. `user` 与 `assistant` 交替的会话缓冲，最多 12 轮。缓冲条目带标记「刚才的对话」。
5. 当前 `user`。

思考记录的字段只有：`depth`、`recalled`、`certainty`、`conflicts`、`novel`、`reply_intent`。`recalled` 为空时，顶层 `certainty` 为 `none`。否则每条 `recalled` 自带 `certainty`，顶层取其中最保守的一档，顺序从保守到开放是 `inferred`、`faint`、`clear`。回答约束按每条自己的态度执行，不按顶层放宽。`reply_intent` 只取 `confirm`、`ask`、`use_memory`、`state_conflict`、`unknown`。有 `conflicts` 时必须是 `state_conflict`；顶层 `certainty` 为 `none` 时必须是 `unknown`；存在 `clear` 或 `faint` 时是 `use_memory`；入选的态度全是 `inferred` 时是 `confirm`；需要用户补充才能写入时是 `ask`。`recalled` 的每个元素还含摘要、类型、阶段、强度、存在时长、压缩层级、激活路径、来源。激活路径是神经元标识和突触类型交替的列表。

首次创建数据库时，在等待第一句输入之前打印：

```text
对话内容和被唤起的记忆会发送给 DeepSeek。
```

打印后把 `privacy_notice_shown` 置 1。该句是 AC-02 的固定文本。

### 7.3 密钥拦截

写入前扫描两项：当前进程的 `DEEPSEEK_API_KEY` 全文，以及正则 `sk-[A-Za-z0-9_-]{16,}`。命中的候选整条丢弃。提示只说这则内容没有记住。

## 8. 配置

环境变量与需求第 11 节一一对应。时长和阈值都由 `dylan.memory.constants` 再导出，业务代码不写散落字面量。

| 环境变量 | 类型 | 默认 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | 字符串，可空 | 空。对话命令拒绝启动 |
| `DEEPSEEK_MODEL` | 字符串 | `deepseek-flash` |
| `DEEPSEEK_BASE_URL` | URL | `https://api.deepseek.com` |
| `DYLAN_DB` | 路径 | `data/dylan.db` |
| `DYLAN_TIMEOUT_SECONDS` | 正整数 | `60` |
| `DYLAN_BUFFER_TURNS` | 正整数 | `12` |
| `DYLAN_RECALL_LIMIT` | 正整数 | `5` |
| `DYLAN_RECALL_CHARS` | 正整数 | `1500` |
| `DYLAN_HOT_CHARS` | 正整数 | `800` |
| `DYLAN_ACTIVATION_THRESHOLD` | 浮点 | `0.2` |
| `DYLAN_DECAY_RATE` | 浮点 | `0.2` |
| `DYLAN_PRUNE_WEIGHT` | 浮点 | `0.05` |
| `DYLAN_PRUNE_INACTIVE_DAYS` | 浮点 | `7` |
| `DYLAN_SOFT_DELETE_GRACE_DAYS` | 浮点 | `7` |
| `DYLAN_DEDUP_JACCARD` | 浮点 | `0.8` |
| `DYLAN_MERGE_JACCARD` | 浮点 | `0.5` |
| `DYLAN_AUTO_DREAM` | 布尔 | `false` |
| `DYLAN_SHOW_THOUGHT` | 布尔 | `false`。为真时把思考记录打到标准错误 |
| `DYLAN_COMPRESS_WITH_MODEL` | 布尔 | `false` |

`DYLAN_AUTO_DREAM=false` 时，正常退出不运行 `dream`。设为 `true` 时，短巩固在第 4 节规定的步骤之后额外运行一次 `dream`。开发命令点名 `dream` 时不受该开关限制。

## 9. 错误与安全

| 类别 | 进程状态 | 是否写对话记忆 |
| --- | --- | --- |
| 缺少密钥 | 对话命令非零退出 | 否 |
| 认证失败、超时、服务错误、网络中断 | 本轮失败，进程保持，等待下一句 | 否 |
| 记忆库损坏或版本拒绝 | 非零退出 | 否 |
| 写入失败 | 进程保持 | 该事务回滚 |
| 密钥形态命中 | 进程保持 | 该条不写 |

程序的文件访问只限：仓库内的 `persona/identity.md`、配置指定的数据库及其同目录锁文件、仓库根目录的 `.env`。不读取剪贴板、屏幕、前台窗口或其他用户文件。

标准错误只写启动失败、本轮失败类别、可选的思考记录和写入警告。标准输出只写隐私说明和 dylan 的回答。

## 10. 可测试性

- 测试通过构造函数注入 `FakeClock` 和假模型，不通过网络，不读取真实 `.env`。
- 假模型按收到的消息回显思考记录中的态度、冲突和记忆摘要。
- 记忆测试使用临时 SQLite 文件。
- 手造图通过仓储的测试辅助函数写入，只在 AC-07 与 AC-20 使用。
- 静态测试扫描 `src/dylan` 的导入和仓库依赖文件，确认第 2.3 节的包名没有出现。
- 真实 DeepSeek 不进入自动测试。手动核对时单独执行，不作为实现完成的阻塞项。需求允许模型用替身验收。

## 11. 命令到技术入口

| 命令 | 密钥 | 模型 | 写入 |
| --- | --- | --- | --- |
| `dylan` | 需要 | 对话与提取会调用 | 每轮提交，正常退出时短巩固 |
| `dylan status` | 不需要 | 不调用 | 只读 |
| `dylan health` | 不需要 | 不调用 | 只读 |
| `dylan decay` | 不需要 | 不调用 | 幂等衰减 |
| `dylan prune` | 不需要 | 不调用 | 修剪。`--dry-run` 回滚 |
| `dylan consolidate --strategy NAME` | 不需要 | 仅当模型压缩开关打开且策略为 `compress` | 该策略。`--dry-run` 回滚 |
| `dylan lifecycle freeze\|thaw\|recover` | 不需要 | 不调用 | 改状态 |
| `dylan reset-identity --yes` | 不需要 | 不调用 | 删除旧身份纤维后按种子重写。不影响用户记忆 |

`lifecycle` 接受 `--id`。未给标识时接受 `--match` 子串；命中不止一条就列出标识和摘要并拒绝修改。

## 12. 实现参数

需求没有单列、但实现必须固定的值：

| 参数 | 值 | 说明 |
| --- | --- | --- |
| 锚点 bigram Jaccard 阈值 | `0.5` | 低于此不成为锚点 |
| 同义闭集 `similar_to` 重量 | `0.6` | 时间锚点初始激活 `1.0` 时，一跳激活为 `0.48`，高于 `0.2` |
| 一次 `dream` 的新建上限 | `3` | 只限制单次运行的写入量，不改变候选定义 |
| 短文本 | 长度小于 2 | Jaccard 记 0；两边规范化后完全相同则记 1 |
| 共激活入库阈值 | 一次召回中的锚点数 ≥ 2 | 与需求第 9.3 节第 6 步一致 |
| `infer` 读取阈值 | `count ≥ 2` | 「多次」的下限 |
| 替代与削弱乘数 | `1.1` 与 `0.7` | 加强角色沿用需求中的 `1.1`；削弱沿用 `0.7` |
| 隐私说明 | 第 7.2 节的固定句 | 验收字符串 |
| 模式版本 | `1` | 首个模式 |

这些值只定义在 `constants` 模块。改变它们必须同时改本文和对应测试。

## 13. 修订

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| 0.1 | 2026-11-03 | 首版，对齐需求规格 0.2 |
| 0.2 | 2026-11-03 | 对齐需求规格 0.3：`ai_inference` 的召回态度上限为 `inferred` |
