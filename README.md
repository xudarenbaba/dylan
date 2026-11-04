# dylan

dylan 是一个跑在本机的命令行对话角色。名字是小写的 dylan。他说的话由 DeepSeek 生成，记得住的事放在本地的一张神经元图里，而不是向量数据库。

每次回答前，他会按这句话唤起相关神经元，沿着突触走到旁边的神经元，再形成一份内部思考记录：哪些记得清楚，哪些只剩一点印象，哪些是他自己推断的，哪些没有印象，以及有没有互相冲突。回答必须遵守这份记录。对话越久，变聪明靠的是这张图在长，而不是重新训练模型。

这一阶段他只能说话。待办会被记住，不会到点提醒。他没有身体，也看不见屏幕。

更完整的约定在 [REQUIREMENTS.md](REQUIREMENTS.md)、[TECHNICAL.md](TECHNICAL.md) 和 [DEVELOPMENT.md](DEVELOPMENT.md)。

## 环境

需要 conda，以及一个 DeepSeek API 密钥。解释器是 Python 3.12，环境名是 `dylan`。

```bash
conda env create -f environment.yml
conda activate dylan
pip install -e .
cp .env.example .env
```

`environment.yml` 只安装依赖。`pip install -e .` 才会装上 `dylan` 这条命令。

打开 `.env`，填上密钥：

```text
DEEPSEEK_API_KEY=sk-你的密钥
```

其余项都有默认值，可以先不动。`.env` 和 `data/` 不会进版本库。

## 对话

在项目根目录执行：

```bash
dylan
```

`dylan chat` 是同一件事。第一次启动会先打印一句：

```text
对话内容和被唤起的记忆会发送给 DeepSeek。
```

然后直接打字，回车发送。空行会被忽略。

结束这次对话用 `exit`、`quit`，或按 `Ctrl-D`。结束时会把这次会话收成一条情景，并做一次短整理。`Ctrl-C` 会立刻停掉，不整理。

可以这样试：

```text
我喜欢深夜写代码
exit
```

下次再打开，问「我晚上适合做什么」。思考记录里应能看到这条偏好，态度不是「没有印象」。

他会记住这些说法：

- 偏好，例如「我喜欢……」
- 事实，例如「我叫……」
- 决定，例如「改成……」
- 边界，例如「不可以……」
- 吩咐，例如「以后……」
- 待办，例如「记着要……」。只保存，不提醒
- 忘掉某句，例如「忘掉香蕉」

寒暄（你好、在吗、谢谢、好的、嗯）和问句不会写成长期记忆。带密钥形态的句子会被丢掉，并提示「这则内容没有记住」。

想看他这一轮的思考记录，在 `.env` 里设 `DYLAN_SHOW_THOUGHT=true`。记录打在标准错误，回答打在标准输出。

## 记忆放在哪

默认数据库是 `data/dylan.db`。身份原文在 `persona/identity.md`。同一个数据库同时只能有一个 dylan 打开。

常用的查看和整理命令：

```bash
dylan status                         # 纤维数、神经元数、身份在不在
dylan health                         # 成熟、连通、新鲜、冲突，以及建议
dylan decay                          # 按时间结算衰减
dylan prune                          # 删掉过弱的突触和过了宽限期的记忆
dylan prune --dry-run                # 只打印数量，不改库
dylan consolidate --all              # 按固定顺序巩固，不含做梦
dylan consolidate --strategy dream   # 单独做一次梦
dylan lifecycle recover --match 香蕉  # 宽限期内恢复
dylan reset-identity --yes           # 只按当前身份文件重写身份
```

`consolidate` 的 `--strategy` 还可以是 `dedup`、`merge`、`enrich`、`infer`、`semantic_link`、`learn_habits`、`summarize`、`mature`、`compress`、`prune`。`lifecycle` 的动作还有 `freeze` 和 `thaw`，用 `--id` 或 `--match` 指定一条。

`status`、`health`、`decay`、`prune`、`consolidate`、`lifecycle`、`reset-identity` 不需要密钥。数据库还不存在时，这些命令不会新建它。

## 测试

```bash
conda activate dylan
pytest
ruff check src tests
```

测试使用假模型和可拨动的时钟，不会访问 DeepSeek。
