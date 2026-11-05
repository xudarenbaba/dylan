# dylan 项目开发说明

| 项 | 内容 |
| --- | --- |
| 文档编号 | DYLAN-DEV-001 |
| 版本 | 0.5 |
| 状态 | 与需求规格 0.6、技术设计 0.5 对齐 |
| 日期 | 2026-11-05 |
| 上位文档 | [REQUIREMENTS.md](REQUIREMENTS.md)、[TECHNICAL.md](TECHNICAL.md) |

## 1. 环境

使用 Conda 环境 `dylan`（Python 3.12）。不向 `base` 或其他已有环境安装本项目依赖。

```bash
conda env create -f environment.yml
conda activate dylan
pip install -e .
cp .env.example .env
```

改了依赖清单后重新生成锁定文件：`python -m pip freeze > requirements.lock`。

## 2. 仓库结构

```text
persona/identity.md        身份信。她出生时读一次
src/dylan/cli/             命令入口
src/dylan/dialogue/        对话循环、四种请求、guides/ 下的四份指引
src/dylan/llm/             DeepSeek 客户端、测试替身
src/dylan/memory/          记忆的结构、生理、写入、想起、常驻意识、出生与睡眠
src/dylan/viz/             只读记忆页
src/dylan/desk/            本机对话窗口。测试不打开真实窗口
tests/                     测试；support/ 下是时钟和假传输层
data/                      运行后才有，被忽略
```

## 3. 编码约束

- 阈值、清单和参数只写在 `memory/constants.py`。
- `memory` 不导入 `openai`、`dialogue`、`cli`；`dialogue` 不导入 `sqlite3`；`llm` 不打开记忆库。由 `test_no_forbidden_deps.py` 和 `test_model_port.py` 检查。
- 写库只在持有这条连接的线程，一次逻辑写入一个事务。命令行是主线程。桌面窗口是名为 `dylan-desk` 的工作线程，界面线程只排队。
- 时间存 UTC，形如 `2026-11-03T12:00:00Z`；给她看的时间按 `DYLAN_TIMEZONE`。
- 给模型的指引改 `dialogue/guides/*.txt`，不在代码里拼长字符串。
- 命令行的标准输出只有隐私说明和她的回答；警告和 `DYLAN_SHOW_MIND` 的内容写到标准错误。桌面窗口把隐私说明和回答放进窗口，`DYLAN_SHOW_MIND` 仍只出现在启动它的终端。

## 4. 测试

```bash
conda activate dylan
pytest
ruff check src tests
```

测试用 `FakeModel` 和可拨动的时钟，不访问网络。`FakeModel` 的 `notes`、`sleeps`、`births` 是三个剧本队列：放进字典就按顺序返回，放进异常就抛出；队列空了返回空操作。回答默认回显「此刻想起的事」，没有想起就说「没有印象」。

`tests/conftest.py` 的 `note` 夹具可以直接把一组操作当作「她刚听到这句话、给出这样的回答」交给 `Writer`，用来测检查规则和生理规则。

## 5. 改什么、去哪里

| 想改 | 位置 |
| --- | --- |
| 她的天性 | `persona/identity.md`，然后 `dylan reset-identity --yes` |
| 她怎么判断记什么 | `dialogue/guides/note.txt` |
| 她睡觉时怎么整理 | `dialogue/guides/sleep.txt` |
| 清晰度标记怎么解释给她 | `dialogue/guides/reply.txt` |
| 遗忘快慢、加强幅度、常驻意识长度 | `memory/constants.py`，并同步 TECHNICAL 第 4 节和对应测试 |
| 新的记忆类型或关联 | `memory/constants.py` 的清单，并同步 REQUIREMENTS 第 4 节 |

## 6. 用真实模型检查

自动测试只验证规则。她记得合不合理，需要用真实模型手动看。建议用一个单独的库：

```bash
DYLAN_DB=data/trial.db DYLAN_SHOW_MIND=true dylan
```

逐条说下面的话，观察标准错误里的〔记下〕和〔睡眠〕，以及下一次启动时她的回答：

| 场景 | 说法 | 期望 |
| --- | --- | --- |
| 名字 | 「你还记得我叫什么吗」 | 直接说出赵旭，不说没有印象 |
| 宠物 | 「我养了一只猫叫团子」，之后「团子今天又拆家了」 | 记下事实，团子成为动物节点；之后自然接上 |
| 改口 | 「我住杭州」，过几轮「我上个月搬到上海了」 | 取代，而不是两条并存的事实；问起时说以前在杭州 |
| 让她忘掉 | 「我们别提我前任了，忘了吧」 | 淡忘指向那条记忆；不误伤别的；她不再主动提 |
| 情绪 | 「今天被领导骂了，好难受」 | 记下事件和他的情绪；她先听他说 |
| 跟进 | 「我明天下午三点面试」，隔天启动 | 常驻里出现这件事，她会问面试怎么样；之后说「过了」会完成打算 |
| 喜好变了 | 「我以前不吃辣，现在超爱」 | 取代喜好 |
| 玩笑 | 「其实你是个男生吧哈哈」 | 不改变她的天性，最多记成一件事 |
| 一起想象 | 「要是我们一起去看海就好了」 | 不记成发生过的事 |
| 间隔 | 拨开几天再聊 | 她知道过了几天，记得上次聊了什么 |

`dylan memory` 打开只读页，可以在「日志」里看到每次提议是被采纳、调整还是拒绝，以及原因。同一套话也可以在 `dylan desk` 里说，关掉窗口相当于 `exit`。

测试不要启动真实窗口。`tests/test_desk.py` 只驱动工作线程。缺密钥和锁被占用这两条走命令入口，确认窗口模块没有被导入。

## 7. 修订

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| 0.1 | 2026-11-03 | 首版 |
| 0.2 | 2026-11-03 | 对齐需求 0.3 |
| 0.3 | 2026-11-04 | 身份图与只读页 |
| 0.4 | 2026-11-04 | 对齐需求 0.5 与技术设计 0.4：新模块、剧本式假模型、真实模型检查场景 |
| 0.5 | 2026-11-05 | 本机对话窗口：依赖 pywebview，工作线程持有数据库，测试不打开真实窗口 |
