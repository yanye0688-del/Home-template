# 可选后端，不重发实现

## Ombre Brain

上游：[P0luz/Ombre-Brain](https://github.com/P0luz/Ombre-Brain)。记忆事实和原文由后端管理。本目录只给部署入口和协调合同，不复制其代码、镜像内容或数据，不替代其许可证与当前文档。

`templates/compose.ombre.example.yaml` 是可选的最小独立服务壳：镜像版本、宿主端口和私有持久目录都要求运行时填写，默认只绑定回环。上游当前 Docker 使用容器8000端口与 `/app/buckets` 持久目录，参见上游README及Dockerfile；这两项来自上游公开接口，不是任何人的主机地址。不要用它覆盖已运行的 compose，不重用别人数据卷，先人工复核所选版本和认证设置。

首次填写与启用由使用者决定；不自动拉镜像、不自动打开公网。真实接入还需完成后端客户端/导出适配器、分页合同、恢复检查。本机只检查模板与协调脚本，不声称已部署这个容器。

## 心潮动态心智

实际上游：[tianyupaipai-cmd/xinchao-dynamic-mind](https://github.com/tianyupaipai-cmd/xinchao-dynamic-mind)。它是可选动态状态层，事实记忆仍由自己的原文档案/后端承担。上游当前文档说明有持续状态与按事件反馈的机制；不要继续假设只有主动上报时才会变化。

接线顺序：在上游服务自己的私有 `.env` 填 `SERVICE_TOKEN`，先验证本机 `/health`；需要远程 MCP 时才启用 `MCP_ENABLED` / `OAUTH_ENABLED` 并设置自己的 HTTPS `OAUTH_PUBLIC_BASE_URL`，连接其 `/mcp`。令牌只在服务端，长期记忆读写开关默认关闭，确需连接才逐项开启。`templates/mind.env.example` 仅列待填/关闭项，不含地址或凭证。

原大纲的逻辑名称不是另一个已验证的仓库地址；此处只指向已核对的作者仓库。按其当前README自行部署，别从别人的运行配置复制 token、回调地址、名字或固定口吻。Node版本、认证、通知和多终端设置以所选上游版本为准，本目录不提供隐含实时接入承诺。

可以向宿主提供短期状态，但不覆盖项目身份文件、长期原文或完整启动取回。提醒、推送、额外模型调用与费用分别确认；本目录不会启用这些服务或配置任何现成个人账号。
