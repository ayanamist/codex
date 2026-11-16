# MCP 配置维护契约

范围：本 fork 的项目 `.mcp.json` 运行时配置。核对日期：2026-11-16；工作区版本：`0.169.0`。
关键词：MCP、JSONC、loader、merge、环境变量、信任、原子替换。
操作示例见 [中文使用手册](usage/project-mcp.md)。

## 当前契约

| 边界 | 要求 |
| --- | --- |
| 发现 | 从已有项目根边界到 cwd 逐级发现 `.mcp.json`；无需 `.codex` 目录。没有项目标记时仅处理 cwd。遵循现有 worktree、信任和管理员约束。 |
| 格式 | 接受 `mcpServers` 包装或裸服务映射，支持 BOM、注释和末尾逗号。错误的包装不能被重新解释成名为 `mcpServers` 的服务。 |
| 传输 | stdio 支持无 type、`stdio`、`local`；HTTP 支持无 type、`http`、`streamable-http`、`streamable_http`。command 与 URL 必须二选一。旧式 SSE 警告并跳过。 |
| 变量 | 在 command、args、env、cwd、URL 和 headers 的值中展开 `${VAR}`、`${VAR:-default}`。空值算已设置；无默认值的缺失变量禁用该服务。使用执行或连接主机的环境。 |
| 路径 | stdio cwd 默认指向声明文件目录；相对 cwd 也基于该目录。命令及脚本参数使用子进程工作目录语义，裸命令由 PATH 查找。 |
| 合并 | 较近目录优先，同目录 TOML 高于 JSON。完整 JSON 定义按服务名整体替换低优先级定义；原生完整传输声明可替换 JSON，原生控制字段仍可叠加。保留 TOML 原有合并语义。 |
| 禁用与错误 | `disabled: true` 或 `enabled: false` 禁用服务，禁用优先。无效、禁用或 SSE 定义遮蔽低优先级同名定义；有效兄弟服务继续加载。整个文件无效时警告并跳过该文件。 |
| 诊断 | 标出文件、服务名和字段；不得输出展开后的秘密值。厂商权限字段不能授予 Codex 权限，不支持的执行或认证扩展必须有诊断。 |
| 刷新 | CLI/TUI 与 app-server 使用一致的有效配置。新会话和完整配置重载重新读取 JSON；不提供自动文件监视。 |

`headers` 映射到 `http_headers`，`disabledTools` 映射到 `disabled_tools`。
OAuth 的 `clientId`、`clientSecret`、`callbackUrl`、`callbackPort` 映射到对应 snake_case 字段；
同时声明别名与原生名称会报错。其余允许字段以解析器的 `SUPPORTED` 列表和
`McpServerConfig` 类型为准。`timeout`、`autoApprove`、`alwaysAllow`、`tools`
等厂商字段会提示忽略；不推测它们的单位或权限含义。

## 源码与测试入口

| 源码 | 责任 |
| --- | --- |
| [`config/src/loader/mod.rs`](../../codex-rs/config/src/loader/mod.rs) | 项目层发现与信任门控 |
| [`config/src/project_mcp.rs`](../../codex-rs/config/src/project_mcp.rs) | JSONC、变量、别名、诊断和禁用占位；内置解析测试 |
| [`config/src/state.rs`](../../codex-rs/config/src/state.rs) | 有效配置合并及被替换字段来源清理 |
| [`config/src/loader/local.rs`](../../codex-rs/config/src/loader/local.rs) | executor-local TOML 投影的替换语义 |
| [`cli/src/mcp_cmd.rs`](../../codex-rs/cli/src/mcp_cmd.rs) | list/get 诊断和全局 add 写入 |
| [`cli/tests/mcp_list.rs`](../../codex-rs/cli/tests/mcp_list.rs) | 子进程级项目发现、list/get 与诊断一致性 |

## 独立边界与限制

插件根目录的 `.mcp.json` 由插件加载器处理，不等同于项目自动发现。
外部客户端迁移将 JSON 转成项目 TOML，不会建立到原 JSON 的持续关联。
`codex mcp add` 写入用户全局配置。
其他客户端的专用文件路径不会因此加入自动发现。

兼容范围是上述共同字段，不能据此宣称与某个客户端所有版本完全兼容。
真实第三方服务、OAuth 和各操作系统的运行结果需分别验证。

## 核对命令

从仓库根目录运行以下只读检查：

```sh
rg -n 'discover_project_layers|project_mcp' codex-rs/config/src/loader/mod.rs
rg -n 'SUPPORTED|ignored vendor|unsupported|fn expand' codex-rs/config/src/project_mcp.rs
rg -n 'Added global MCP server|ConfigEditsBuilder::new' codex-rs/cli/src/mcp_cmd.rs
git diff --check
```

在约定的构建环境中，从仓库根目录执行对应测试：

```sh
cargo test --manifest-path codex-rs/Cargo.toml -p codex-config --lib
cargo test --manifest-path codex-rs/Cargo.toml -p codex-cli --test mcp_list
```

以上为复核入口，不表示本次文档整理重新执行了运行时验证。
