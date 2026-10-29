# 后端适配合同

所有适配器都是运行在本机的**已配置 argv 数组**，不经过 shell。协调器把一条 JSON 请求写入 stdin，只接受 stdout 的一条 JSON 对象；日志去 stderr，不能混在结果里。超时、非法 JSON、超出输出边界都失败，不截断后冒充完整读取。配置中的可执行程序要先审查，它本身拥有调用者的本机权限，本工具不是隔离恶意程序的沙箱。

请求共同字段：`operation`。依操作另有 `offset/limit`、`id/query`、`text/operation_id`。原文经过 stdin，不拼进 shell 命令。

| operation | 返回合同 |
|---|---|
| surface | `{"items":[{"id":"...","content":"全文"}]}`；真实浮现结果 |
| letters | 同上；最新信件，最多请求的 limit，不能把摘要当全文 |
| self | `{"snapshot_sha256":"...","total":0,"entries":[],"next_offset":null}`；所有批次同快照，总数准确 |
| recall | 精确 id 时 `{"id":"...","content":"全文"}`；query 时 `{"items":[...]}` |
| pins | items，另含布尔 pinned/resolved/protected；消化脚本只提供待审建议 |
| note | 接收 text/operation_id，真正逐字写入并返回 id；相同 operation_id 幂等；协调器随后 recall 精确核对 |
| backup_export | `{"path":"私有一致性导出文件","sha256":"..."}`；路径在工作区内，必须是后端的稳定一致性导出 |

## 可运行的只读导出模式

配置例子连接 `scripts/export-adapter.py`。使用者先从自己的后端/宿主完整导出，下列文件放进私有 `private-exports/`：

- surface.json、letters.json、pins.json、memories.json：上述 items 对象。
- self.json：`{"entries":[{"id":"self-example","content":"完整的一条"}]}`。

示例适配器只读这些**明确准备好的文件**，不扫描 OB、浏览器或聊天记录。它对全部自我认知条目计算稳定快照并分页，精确 recall 只匹配 id。不会实现 note 写入；写入必须由用户显式接到真实后端，不能偷偷在导出副本里写一条就当已进原库。

每次启动前刷新导出。静态导出只能证明“这份导出已读齐”，不能证明远端此刻未变化；需实时一致性的用户应配置实际客户端适配器。不要给导出模式贴“已与实时后端验收”的标签。

一个后端需要变更协议时，先用虚构库验合同，再改运行时配置。密钥只通过其本机私有配置或环境注入，不进入示例 argv、文档、日志或本仓库。这里不重发第三方服务实现。
