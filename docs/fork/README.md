# 本 fork 文档

本目录说明 `ayanamist/codex` 的使用方式和维护契约。功能演进和修改历史通过 Git 查看。

## 中文使用手册

| 文档 | 内容 | 关键词 |
| --- | --- | --- |
| [安装与更新](../install.md) | 支持的平台、首次安装、指定版本、从官方版本迁移、更新和日志 | 安装、迁移、PATH、`codex update` |
| [项目 MCP 配置](usage/project-mcp.md) | 直接使用项目 `.mcp.json`，配置本地进程或 HTTP 服务，处理变量和覆盖规则 | MCP、JSONC、headers、环境变量、信任 |
| [Skill 配置](usage/skills.md) | 启用或禁用 skill，控制自动调用，设置全局和工作区规则 | skills、`skills.config`、`projects`、调用策略 |
| [Linux 沙箱目录清理](usage/linux-sandbox.md) | 了解临时空目录、自动恢复条件和保留边界 | Linux、bubblewrap、空目录、异常退出 |
| [对话文件链接](usage/file-links.md) | 查看绝对路径、用内置查看器或宿主编辑器打开文件 | TUI、`file_opener`、`TERM_PROGRAM`、Zed |

## 维护参考

维护文档保留当前实现契约、源码入口、限制和核对命令，供代码审查、升级和排障使用。

| 文档 | 内容 | 关键词 |
| --- | --- | --- |
| [MCP 配置契约](project-mcp-configuration.md) | 项目配置发现、解析、原子替换、信任和插件配置边界 | loader、merge、MCP、兼容性 |
| [Skill 策略契约](skill-invocation-policy.md) | 策略优先级、发现路径、缓存和配置编辑 | policy、executor、plugins、cache |
| [沙箱清理契约](sandbox-mount-targets.md) | 挂载点身份记录、并发所有者和安全删除条件 | inode、identity、cleanup、SIGKILL |
| [构建与发布](release-management.md) | 三平台独立发布、Linux/Windows 就绪后自动晋升稳定版、打包、辅助程序复用、构建缓存及并发与跨编译边界 | release、GitHub Actions、V8、rust-cache、prerelease、latest、CARGO_BUILD_JOBS、cross compilation |
| [工作流入口](../../.github/workflows/README.md) | 平台工作流位置、手动运行、失败重跑和发布通道 | workflow、dispatch、latest |

范围：本 fork 的扩展及分发方式；按当前源码整理于 2026-11-16，工作区版本 `0.169.0`。
这些说明不代表机器上已安装的 CLI 或已发布版本已包含所有当前源码功能。
