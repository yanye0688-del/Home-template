# 备份：先加密，再明确上传

`backup-memory-to-github.sh` 默认只在本机生成 GPG 公钥加密的包。需要已审查、可信的完整收件公钥指纹；指纹放使用者运行时，不放分发示例。没有 GnuPG 或公钥不可信会失败，不跳过加密、不改变信任模型。

```sh
advanced/scripts/backup-memory-to-github.sh --recipient PUBLIC_KEY_FINGERPRINT
```

只收 config.backup.sources 明确列出的稳定文件；不递归打包整个家，不收 .env/私钥/token/活的数据库文件。Ombre 等后端优先使用其**官方一致性导出**，通过 backup_export 适配器交回稳定文件和 hash；不要 cp 正在写入的 SQLite 文件。没有一致性保证就如实说还不能验收。

包里包含逐文件 hash 清单；临时明文只在私有 state 目录，结束清理，留下 .gpg 与本机报告。脚本默认 restore_verified=false。实际解密到一个新的私有目录、核对清单与样本，验证可读后，才能把该包写进 handoff facts，并由操作者明确标记恢复抽查已做。不要解压覆盖运行中的真实库；tar 包只接受自己可信来源，先查成员名和路径。

上传是另一个显式选择：

```sh
advanced/scripts/backup-memory-to-github.sh --recipient PUBLIC_KEY_FINGERPRINT --upload
```

先在私有运行时配置填已有的 `backup.repository` 和 `backup.branch`，凭证只从指定环境变量取。程序会先查 GitHub API，确认 private=true，才将**密文**放进新文件；不会创建仓库、改可见性、覆盖原路径、force-push 或删除备份。不存在的分支需操作者先自行确认创建；模板不替你选账号或仓库。单文件上限20MiB，超过就在本地保留，不自动分片外传。

上传后的 blob hash 要与密文一致。失败时可能已生成本地密文；先看本机结果，不能盲目重试或把返回200当成已恢复验收。GitHub 私密性最终由仓库所有者管理；后续可见性变更不由这个脚本保证。

加密不等于发布许可。记忆、聊天、截图、个人关系和密钥都不属于模板材料，禁止把运行时目录回拷到 advanced/；也不要把含凭证的旧脚本贴到外部服务请它“帮脱敏”。
