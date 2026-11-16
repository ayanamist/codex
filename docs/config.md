# Configuration

For basic configuration instructions, see [this documentation](https://developers.openai.com/codex/config-basic).

For advanced configuration instructions, see [this documentation](https://developers.openai.com/codex/config-advanced).

For a full configuration reference, see [this documentation](https://developers.openai.com/codex/config-reference).

## 本 fork 的项目 MCP 配置

受信任项目可以直接使用 `.mcp.json`，支持本地进程和 Streamable HTTP、
环境变量、headers、注释和末尾逗号。
文件位置、配置示例和覆盖规则见 [中文使用手册](fork/usage/project-mcp.md)。
实现边界和源码入口见 [MCP 配置维护契约](fork/project-mcp-configuration.md)。

## Lifecycle hooks

Admins can set top-level `allow_managed_hooks_only = true` in
`requirements.toml` to ignore user, project, and session hook configs while
still allowing managed hooks from requirements and managed config layers. This
setting is only supported in `requirements.toml`; putting it in `config.toml`
does not enable managed-hooks-only mode.
