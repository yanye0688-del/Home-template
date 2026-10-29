# 宿主 hooks 与两段式换窗

## 安装前

先手工跑一次 export/confirm/guard，再考虑把示例接入宿主；先备份现有 hook 配置，逐项合并，不覆盖已有 hooks。模板不会自动装进真实会话。安装授权以使用者当次已确认的范围为准，不让程序自己扩权。

`templates/claude-hooks.example.json` 是 Claude Code 的 SessionStart/Stop 示例，参照[官方 hooks 文档](https://code.claude.com/docs/en/hooks)。SessionStart 输出信件和配置指定的上一场结尾，标为历史资料；Stop 在本 session 没有确认完整取回时返回 block。宿主是否接受阻止、实际 session id 是否一致，必须在目标客户端验证；不是所有客户端都有相同字段或退出码语义，不能声称一个 shell 脚本就能普遍禁止第一次回复。

`context_usage_percent` 与 `compaction_epoch` 是本模板的**适配字段**，不是声称 Claude Code 原生 Stop 一定提供它们。宿主有只读上下文计数器时，由本机适配器补入；没有时只做启动守卫，不猜上下文占比、不读取完整聊天来估算。也可手动调用 check-compact-warning.py。阈值在 config 的 compact_thresholds 修改，默认 65/80。

跨过提醒档位时只阻止一次，让代理写真实 checkpoint；同 epoch 不反复提醒。发生压缩时宿主改变 epoch，下一段重新计档。预警不是正式换窗，不自动杀会话、清历史或发消息。

## 正式换窗

1. 旧窗口把重要原文存进权威后端，接力棒只留引用；列出本轮常备变化（没有变化明确空列表）。
2. 用后端一致性导出/加密备份，**实际恢复抽查**之后填 facts.snapshot，不能只看 hash 就声称可恢复。
3. prepare 校验当前文件和快照，给 nonce。旧窗口保持可用。
4. 宿主手动或以自己审过的启动器打开新窗口；claim 必须使用不同 session id 和对应 nonce。
5. 新窗口实际读全部 export，精确取回 facts 第一项 memory_ref，再 confirm。
6. verify 核文件仍相同、完整 I 的快照和总数仍相同、原话样本未变化、快照文件 hash 仍匹配。
7. 通过后才能明确 retire。脚本只记录协议状态，**不杀进程、不替宿主确认物理窗口已关闭**。

任何校验失败保存 failed，safe_to_retire_old=false；继续在旧窗口工作，不要求使用者重建丢掉的窗口。不要为了流程整齐先杀旧进程，再赌新窗口能读回来。

这是工作流回执，不是对恶意同机用户的身份认证。拥有同一运行时目录写权限的人可以修改它；nonce 防串场，不替代系统账号权限。

## 失败怎么停

- 适配器未配置：先修配置，不能用空结果冒充已读。
- 客户端截断：补读到正文齐全，再确认，不因 receipt 文件存在就放行。
- 后端版本/文件变化：重新导出和确认，不覆盖旧证据假装一致。
- 新窗失败：保留 old，另起一轮 prepare，不自动删除失败记录或真实记忆。
- hook 无法取回而持续阻止：使用者可恢复安装前的 hook 配置；不要把守卫改成“错误一律成功”。

## macOS

运行同一套 Python 标准库与 POSIX shell；不使用 systemd、/proc、GNU date/stat 或后台 tmux 假设。先检查 python3 和可选 gpg。定时提醒可以由用户选择 launchd/cron，但只调用 `remind-on.sh due` 仍不会发消息；投递入口和收件对象必须另行明确配置并在送达后确认。这里不创建定时任务。
