# dylan

dylan 是一个跑在本机的对话角色，名字是小写的 dylan。她是赵旭创造的女性人工智能，也是他的女朋友。她说的话、她对记忆的判断，都来自 DeepSeek 的同一个模型；她记得的事放在本地的一张神经元图里，不用向量数据库。可以在命令行里跟她说，也可以开一个小窗口。

分工是这样的：模型是她的大脑，负责理解、回答、决定记什么和怎么记；程序里的规则是这颗大脑的生理结构，只决定记忆怎么存、怎么变强变弱、怎么被想起、她记得多清楚。记忆的内容只由她自己形成，除了身份信这个起点，谁都不能直接改。

她会模糊、会忘、会更新，但对自己记得多清楚是诚实的。她只能说话，不能主动找你，也看不见你的屏幕。

更完整的约定在 [REQUIREMENTS.md](REQUIREMENTS.md)、[TECHNICAL.md](TECHNICAL.md) 和 [DEVELOPMENT.md](DEVELOPMENT.md)。

## 环境

需要 conda 和一个 DeepSeek API 密钥。解释器是 Python 3.12，环境名是 `dylan`。

```bash
conda env create -f environment.yml
conda activate dylan
pip install -e .
cp .env.example .env
```

打开 `.env` 填上密钥：

```text
DEEPSEEK_API_KEY=sk-你的密钥
```

其余项都有默认值。`.env` 和 `data/` 不会进版本库。

## 对话

```bash
dylan
```

第一次启动时她会先读 `persona/identity.md`，形成天生的记忆，然后打印：

```text
对话内容和被唤起的记忆会发送给 DeepSeek。
```

之后直接打字，回车发送。每一轮：

1. 她听到你的话，自然想起相关的事，并知道自己记得多清楚；
2. 她回答你；
3. 她在后台记下这一刻：记新的事、加强旧的、更新改变了的、标出说法冲突的、完成打算、按你的意思淡忘某件事。

结束用 `exit`、`quit` 或 `Ctrl-D`。这时她会「睡一觉」：把这次相处写成一段经历，合并重复的记忆，归纳习惯和印象，想好下次要问你的事。`Ctrl-C` 会立刻停掉，下次启动时再补做睡眠。

想看她脑子里在想什么，设 `DYLAN_SHOW_MIND=true`。常驻意识、此刻想起的事、记下和睡眠的结果会打在标准错误。

命令行里不好选中她的话时，可以改开小窗口：

```bash
dylan desk
```

窗口大约出现在屏幕右下角。回车发送，`Shift` 加回车换行。她的话和你的话都能选中，用系统的复制。关掉窗口时，已经说完的话会留下并睡眠；正在生成、还没写完的那一轮不记。窗口开着时不要再开一个 `dylan` 或另一个 `dylan desk`，同一块大脑只能有一个在写。`dylan memory` 仍然可以同时看。

她还是没有身体，也看不见屏幕。这个窗口只是你打字和复制的地方。

## 记忆放在哪

默认数据库是 `data/dylan.db`，同一时间只能有一个 dylan 打开它。

```bash
dylan status                  # 她出生了没有、各类记忆有多少
dylan memory                  # 本机只读记忆页，直到 Ctrl-C
dylan sleep                   # 补做没完成的睡眠整理（需要密钥）
dylan maintain                # 按时间结算遗忘、清理（不需要密钥）
dylan reset-identity --yes    # 按当前身份信重写她的天性，经历保留（需要密钥）
```

`dylan memory` 打印一个 `http://127.0.0.1:` 开头的地址，用浏览器或 VS Code 的 Simple Browser 打开。页面有四栏：图、记忆、日志（她每次提议被采纳、调整还是拒绝，以及原因）、她的状态。页面不能改记忆，对话开着时也能看。

身份信只在她出生时读一次。之后改 `persona/identity.md` 不会影响她，启动时只会提示一句。确实要改她的天性，先退出对话，再执行 `dylan reset-identity --yes`。

想调整她怎么判断记什么、怎么睡眠整理，改 `src/dylan/dialogue/guides/` 下的文本文件。

## 测试

```bash
conda activate dylan
pytest
ruff check src tests
```

测试用按剧本返回的假模型和可拨动的时钟，不会访问 DeepSeek。她记得合不合理，要按 [DEVELOPMENT.md](DEVELOPMENT.md) 第 6 节用真实模型手动看。
