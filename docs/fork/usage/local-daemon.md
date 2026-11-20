# 本地后台服务

适用于本 fork 的交互式 CLI。本文于 2026-11-20 按工作区版本 `0.171.0` 编写。

| 命令 | 行为 |
| --- | --- |
| `codex` | 使用内嵌服务，即使本地 daemon 已在运行 |
| `codex --no-daemon` | 显式使用内嵌服务 |
| `codex --no-daemon=false` | 允许探测并复用本地 daemon，自动启动仍由原有启动条件决定 |

`resume`、`fork` 和 `agents` 支持相同的交互启动选项。参数可以写在子命令前或后，两处均指定时，以子命令上的值为准。显式 `--remote` 仍可直接选择远程端点。

普通交互会话在 `features.daemon_auto_start = false` 时，仍可通过 `--no-daemon=false` 连接已有 daemon。启动配置必须符合共享服务的兼容性要求。`agents` 显式启用 daemon 后仍按其原有逻辑请求自动启动。

实现见 [启动流程](../../../codex-rs/tui/src/startup_orchestration.rs)，回归场景见 [默认内嵌服务](../../../codex-rs/tui/tests/suite/focus_palette.rs)和[复用已有 daemon](../../../codex-rs/cli/tests/daemon_startup.rs)。可从仓库根目录在构建环境运行以下验证命令。

```sh
cargo nextest run --manifest-path codex-rs/Cargo.toml -j 1 -p codex-cli --bin codex --test daemon_startup \
  -E 'test(resume_and_fork_preserve_no_daemon) | test(discovered_managed_daemon_can_restart_with_auto_start_disabled)'
cargo nextest run --manifest-path codex-rs/Cargo.toml -j 1 -p codex-tui --test all \
  -E 'test(default_embedded_skips_daemon_startup_and_discovery)'
```
