# 进阶记忆：可选安装，不替换基础版

基础版的三个 Markdown 文件、两个脚本继续照常用。本目录提供通用方法、带校验的本地协调脚本和可选后端接法，不携带任何人的记忆、口吻、身份设定、聊天或密钥。

## 先让使用者知道会做什么

安装到使用者自己的电脑前，先说明将新增哪些文件、连接哪个后端、备份去哪里；取得该使用者对这次安装的授权。不要因为拿到了模板就自动改其现有配置、启动服务或加定时任务。本目录里的安装示例不是对当前环境的操作指令。

## 先读这五份

1. [三层分工](methods/three-layer-memory.md)
2. [开机顺序](methods/boot-order.md)
3. [接力棒写法](methods/baton-guide.md)
4. [失忆读者测试](methods/amnesia-reader-test.md)
5. [钉选与实际浮现](methods/pin-and-verify.md)

进阶脚本的重点是：原文只存一份、现场保持短、核验读取是否完整、失败仍有旧窗口可用。脚本不会证明模型已经理解，模型读完正文后的确认不能省略。

## 依赖与本机检查

Python 3.10+、POSIX shell（macOS/Linux）。核心只用标准库；加密备份另需 GnuPG。没有自动安装依赖。先检查 `python3 --version`；macOS 上不要假设系统已经带合适版本，安装方式先和使用者确认。

```sh
python3 -m unittest discover -s advanced/tests -v
python3 advanced/scripts/audit-template.py advanced
```

测试只在临时目录生成虚构资料，不接真实记忆、账号或远端。Linux 运行结果可以确认；macOS 用的是兼容写法，仍需在目标 Mac 运行同一组检查，不能把语法兼容说成真机通过。

## 放进自己的家目录

保留原来的 `CLAUDE.md` 与 `OB/`。把本目录放到家目录的 `advanced/`，先复制 `templates/config.example.json` 到家目录的私有 `runtime-config.json`，按真实位置填写。配置中的路径以该配置文件所在目录为基准；不要照抄任何人的绝对路径。

```sh
export MEMORYKIT_CONFIG="$(pwd)/runtime-config.json"
```

不要把这个运行时配置、`.memorykit-state/`、`private-exports/` 提交到模板仓库。`templates/distribution.gitignore.example` 是供人工合并的示例，不覆盖原 `.gitignore`，也不改变原有本地 Git 快照策略。

## 先决定怎样接记忆后端

[适配合同](adapters.md)说明了 JSON stdin/stdout。默认示例是**只读、显式准备的私有导出适配器**：`private-exports/` 由宿主从真实后端完整导出，脚本不会扫描聊天或偷偷连模型。导出文件必须在本次启动前刷新；它验证的是这份导出，不会假装已经确认后端此刻没有变化。

有真实本地 CLI/MCP 客户端时，可把对应命令数组填入 adapters，直接读取后端。没有标准的“在 shell 里调用当前会话 MCP 工具”命令，不要编一个。未配置、缺字段、截断、翻页中快照变化都会返回非零，不标启动成功。写入 `note` 需另配实际后端适配器；示例只读适配器会拒绝写入，不会造一个成功回执。

### 一次完整启动

把后端的 surface、letters、全部 self、memories、pins 完整导出成 [约定格式](adapters.md)。再执行：

```sh
python3 advanced/scripts/memorykit.py --config runtime-config.json orientation export --session candidate --sample EXISTING_MEMORY_ID
```

工具输出身份说明、真实浮现、最新信、接力棒、常备、**全部**自我认知和一条精确记忆正文。输出过长而客户端截断时，先补读，不要确认。读完每一段正文、核对总数/快照后才执行：

```sh
python3 advanced/scripts/memorykit.py --config runtime-config.json orientation confirm --session candidate --confirm-read
MEMORYKIT_CONFIG="$MEMORYKIT_CONFIG" advanced/scripts/check-orientation.sh --session candidate
```

`session` 必须来自宿主当前会话的可靠标识，不能每次都抄示例里的 candidate。确认不是身份认证、不是模型理解的自动证明，是当前代理对实际读齐的明确回执。

### 两段式换窗

见 [换窗与 hooks](hooks-and-handoff.md)。先写接力棒、存重要原话并取得引用、列出常备变化、生成并实际恢复抽查快照。按 `templates/handoff-facts.example.json` 填真实证据。

```sh
advanced/scripts/handoff.py prepare --session old-session --facts handoff-facts.json
advanced/scripts/handoff.py claim --session new-session --nonce NONCE_FROM_PREPARE
# 新窗口亲自做前述 export/confirm，sample 使用 facts.memory_refs 的第一项
advanced/scripts/handoff.py verify --session new-session --nonce NONCE_FROM_PREPARE
advanced/scripts/handoff.py retire --session old-session --nonce NONCE_FROM_PREPARE --confirm
```

这些命令需要前面已设定 MEMORYKIT_CONFIG。**旧窗口一直保留到 verified；任何自检失败进入 failed，继续用旧窗口。** retire 也只记录状态，脚本不杀进程、不替你启动会话。宿主层明确确认新窗口可用后，才安排旧窗口退役；没有宿主适配时手动操作。

### 其它入口

- `check-compact-warning.py --session SESSION --epoch COMPACTION_EPOCH --percent 70`：本地 65/80 提前提醒，每个 epoch 同一档只提醒一次，不代表平台官方压缩阈值。
- `session-start-letters.sh`：最新六封信和配置指定的上一段结尾，全文逐字输出；没有任何内置私人句子。
- `memorykit.py --config runtime-config.json pin-check EXISTING_MEMORY_ID`：真调用一次浮现，检查目标 id 是否回来；不靠 pinned 标签猜结果。
- `ombre-digest.sh`：只列“已解决、仍钉选、非保护项”的待审 id，默认不解除钉选、不删内容。用户确认后通过真实后端工具处理，再重新浮现复核。
- `remind-on.sh add --id reminder-demo --at 2030-01-01T09:00:00+08:00 --text '读一章书'`，`remind-on.sh due`：只记明确约定的提醒和列到期项，不发消息；真正送达后 `done --id reminder-demo --confirm`。
- `check-ob-bloat.sh`：只统计配置范围内 Markdown 的相对路径与字节数，不读出正文、不自动裁剪。
- `recall.sh '要查的词'`：交给已配置后端检索。未命中不表示没有发生过。
- `memory-note.sh --operation-id stable-note-id --text '要原样存入的内容'`：需真实写适配器，写后精确回读；回读失败不自动重试。
- [加密备份](backup.md)：先本地加密并恢复验证，上传是另一个显式动作。

## 完成的含义

本目录自身的本地测试通过，不等于已接好使用者的后端、已配置宿主 hooks、Mac 已跑过或远端备份可恢复。每一层分别报告：文件已写／本机检查／真实后端／宿主 hook／恢复抽查。不要为了显示全绿编出回执。

## 第三方项目

只连接或指向上游，不打包其实现、数据和依赖，不暗示上游作者认可此模板：
- [Ombre Brain](https://github.com/P0luz/Ombre-Brain)：记忆后端，遵从其许可证与当前部署文档。
- [心潮动态心智](https://github.com/tianyupaipai-cmd/xinchao-dynamic-mind)：独立动态状态层，见 [可选接法](optional-backends.md)。

原仓库根目录基础版保持原样。这里没有任何人的专有服务、手机控制、私人资料或现成账号配置。
