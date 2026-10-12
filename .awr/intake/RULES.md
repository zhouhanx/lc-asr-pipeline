# 凭据不进入 AWR 或日志 {#no-secrets severity=hard scope=project value=*}

真实口令、访问令牌、模型凭据和环境赋值只留在本地环境与密钥管理中。AWR 来源、日志和交接记录只使用变量引用或已脱敏描述。不得为了通过扫描而关闭检查。

# 操作必须可追踪 {#operation-identity severity=hard scope=project value=*}

每个 HTTP 请求使用服务端生成的操作标识，并在响应头、CORS 和安全日志中保持同一个标识。持久业务另有稳定领域标识。日志不得包含查询字符串、请求体、凭据、签名链接或私人文档内容。来源：根目录 `AGENTS.md` 的操作身份约束。

# 交接状态以 2026-07-24 状态页为准 {#status-authority severity=hard scope=project value=*}

当前产品状态以 `llm-repo/wiki/lc-asr-pipeline-status.md` 和 `llm-repo/output/session-archive-2026-07-24-closeout.md` 为准。`llm-repo/fplan.md` 与根目录 `AGENTS.md` 中更早的阶段描述只作为历史来源；未勾选或旧的下一步不能覆盖后来已记录的完成事实。

# 不把占位页面当成已完成管理功能 {#no-placeholder-completion severity=hard scope=project value=*}

租户内 Members、Roles、Settings 仍是占位。平台级开户已经独立实现。PPT 撰写只保留入口。不要在未实现验收前把这些入口记为完成。
