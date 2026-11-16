# 安装与更新

本页介绍 `ayanamist/codex` 的独立安装包。功能配置见 [中文使用手册索引](fork/README.md)。

## 支持的平台

| 平台 | 发布包 | 要求 |
| --- | --- | --- |
| Linux x86_64 | `codex-package-x86_64-unknown-linux-gnu.tar.gz` | glibc 2.38 或更新 |
| macOS Apple Silicon | `codex-package-aarch64-apple-darwin.tar.gz` | ARM64 |
| Windows x64 | `codex-package-x86_64-pc-windows-msvc.tar.gz` | 原生 Windows，使用 PowerShell 安装 |

当前发布配置不生成 Linux ARM64、Intel macOS、Windows ARM64 或 musl/Alpine 包。
WSL 按 Linux 要求处理。

## 首次安装

macOS 或 Linux：

```sh
curl -fsSL https://github.com/ayanamist/codex/releases/latest/download/install.sh | sh
```

Windows PowerShell：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://github.com/ayanamist/codex/releases/latest/download/install.ps1 | iex"
```

安装器从 [本 fork 的 GitHub Releases](https://github.com/ayanamist/codex/releases/latest)
下载最新稳定包并校验 SHA-256。包内包含 CLI、辅助程序和运行资源，应保持完整。

安装完成后按终端提示配置 PATH，或打开新终端，再确认版本并启动：

```sh
codex --version
codex
```

Fork 版本使用 `<上游版本>-fork.<提交前八位>` 的形式。

## 指定版本

将 `VERSION` 替换成 Releases 页面已有的版本号，可以带或不带 `rust-v` 前缀。
Unix 安装器接受 `--release`：

```sh
curl -fsSL https://github.com/ayanamist/codex/releases/latest/download/install.sh | sh -s -- --release VERSION
```

PowerShell 使用 `CODEX_RELEASE` 环境变量：

```powershell
$env:CODEX_RELEASE = 'VERSION'
try {
    irm https://github.com/ayanamist/codex/releases/latest/download/install.ps1 | iex
} finally {
    Remove-Item Env:CODEX_RELEASE
}
```

Unix 也支持 `CODEX_RELEASE`。指定版本只控制该次安装，不会锁定后续 `codex update`。
预发布版本可以显式选择，但不会自动成为默认 latest 稳定通道。
当前自动发布流程生成的是预发布版本；在维护者将其晋升稳定版之前，
默认安装和 `codex update` 继续使用此前的稳定版。
需要使用预发布版本时，按本节显式指定版本安装。

## 安装路径

| 内容 | 默认位置 |
| --- | --- |
| macOS/Linux 命令 | `~/.local/bin/codex` |
| Windows 命令 | `%LOCALAPPDATA%\Programs\OpenAI\Codex\bin\codex.exe` |
| 完整包 | `$CODEX_HOME/packages/standalone`，默认 `~/.codex/packages/standalone` |

通过 `CODEX_INSTALL_DIR` 可以改变命令目录。
如果终端仍使用其他版本，检查实际命令来源：

```sh
command -v codex
codex --version
```

Windows：

```powershell
Get-Command codex -All
codex --version
```

## 从官方版本迁移

运行上面的 fork 安装器。它可以检测冲突的包管理器安装，并在确认后卸载旧安装。
如果保留了旧安装，检查 PATH 中的顺序，确认运行的是 fork 的独立安装版本。

`chatgpt.com` 安装器、npm 的 `@openai/codex` 和 Homebrew 的 `codex` cask
提供官方分发。通过这些来源更新会回到官方版本。
本 fork 的 `codex update` 会拒绝通过 Homebrew、npm、pnpm、Bun 或 Vite+ 自动更新，
并提示迁移到独立安装。

## 后续更新

使用 fork 独立安装后运行：

```sh
codex update
```

再次运行 fork 安装器也可以更新。
更新命令和托管 daemon 的安装更新都使用本 fork 的 GitHub Releases。
如果使用 debug 构建或无法识别的安装布局，按提示手工安装。

启动时的版本提示有本地缓存，只提示高于当前版本的发布序号；
后台检查结果在下次启动时使用。`codex update` 本身不依赖该提示缓存。
没有用于切换更新仓库或安装器地址的 `config.toml` 设置。

## 诊断日志

TUI 默认将诊断保存在有容量限制的本地存储中。
需要文本日志时，可显式设置日志目录：

```sh
codex -c log_dir=./.codex-log
tail -F ./.codex-log/codex-tui.log
```

可用 `RUST_LOG` 调整 Rust 日志级别。
非交互模式 `codex exec` 默认使用 `RUST_LOG=error` 并直接输出日志。

## 源码开发与维护

源码构建和发布契约见 [构建与发布维护参考](fork/release-management.md)，
通用开发说明见 [Rust 工作区说明](../codex-rs/README.md)。
