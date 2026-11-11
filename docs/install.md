## Installing & building this fork

### Install from GitHub Releases

The `ayanamist/codex` fork publishes standalone packages for these targets:

| Platform | Release package | Requirement |
| --- | --- | --- |
| Linux x86_64 | `codex-package-x86_64-unknown-linux-gnu.tar.gz` | glibc 2.38 or newer |
| macOS Apple Silicon | `codex-package-aarch64-apple-darwin.tar.gz` | ARM64 |
| Windows x64 | `codex-package-x86_64-pc-windows-msvc.tar.gz` | Native Windows, PowerShell installer |

Linux ARM64, Intel macOS, Windows ARM64, and musl/Alpine packages are not
currently published. WSL follows the Linux requirements.

On macOS or Linux:

```sh
curl -fsSL https://github.com/ayanamist/codex/releases/latest/download/install.sh | sh
```

On Windows, run in PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://github.com/ayanamist/codex/releases/latest/download/install.ps1 | iex"
```

These scripts resolve the latest published stable release in
[`ayanamist/codex`](https://github.com/ayanamist/codex/releases/latest) and verify
downloaded packages with SHA-256. The packages include the CLI and its companion
executables and resources; keep the complete package together. The fork does
not publish the upstream standalone `codex` DotSlash release asset.

To select a specific published release, set `CODEX_RELEASE` to its version
(with or without the `rust-v` prefix). For example, to install the release
observed on 2026-11-11:

```sh
curl -fsSL https://github.com/ayanamist/codex/releases/latest/download/install.sh | CODEX_RELEASE=0.167.0-fork.aeae161d sh
```

```powershell
$env:CODEX_RELEASE = '0.167.0-fork.aeae161d'
try {
    irm https://github.com/ayanamist/codex/releases/latest/download/install.ps1 | iex
} finally {
    Remove-Item Env:CODEX_RELEASE
}
```

This selects the installation version for that invocation; it does not pin
future `codex update` calls. Unix also accepts `sh -s -- --release VERSION`.

### Install paths, migration, and updates

The default command location is `~/.local/bin/codex` on macOS/Linux and
`%LOCALAPPDATA%\Programs\OpenAI\Codex\bin\codex.exe` on Windows. Set
`CODEX_INSTALL_DIR` to override the command directory. Package contents live
under `$CODEX_HOME/packages/standalone` (`~/.codex/packages/standalone` by default).
The installer configures PATH; follow its terminal instructions or open a new
terminal before running Codex.

The official `chatgpt.com` installers, npm package `@openai/codex`, and Homebrew
cask `codex` install OpenAI's distribution. To migrate to this fork, run the fork
installer above. It detects conflicting package-manager installations and can
offer to uninstall them with confirmation. If an old installation remains,
check which executable your shell selects:

```sh
command -v codex
codex --version
```

```powershell
Get-Command codex -All
codex --version
```

Current fork versions include a suffix such as `-fork.aeae161d`. Once using the
fork's standalone installation, update with:

```sh
codex update
```

Running the fork installer again also updates it. See
[CLI installation and update sources](fork/updates.md) for the source contract
and verification evidence.

### Build from source

```bash
# Clone the repository and navigate to the root of the Cargo workspace.
git clone --branch fork-release https://github.com/ayanamist/codex.git
cd codex/codex-rs

# Install the Rust toolchain, if necessary.
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/env"
rustup component add rustfmt
rustup component add clippy
# Install helper tools used by the workspace justfile:
cargo install --locked just
# DotSlash fetches pinned development tools such as buildifier on first use.
cargo install --locked dotslash
# Install nextest for the `just test` helper.
cargo install --locked cargo-nextest

# Build Codex.
cargo build

# Launch the TUI with a sample prompt.
cargo run --bin codex -- "explain this codebase to me"

# After making changes, use the root justfile helpers (they default to codex-rs):
just fmt
just fix -p <crate-you-touched>

# Run the relevant tests (project-specific is fastest), for example:
just test -p codex-tui
# `just test` runs the test suite via nextest:
just test
# Avoid `--all-features` for routine local runs because it increases build
# time and `target/` disk usage by compiling additional feature combinations.
```

## Tracing / verbose logging

Codex is written in Rust, so it honors the `RUST_LOG` environment variable to configure its logging behavior.

The TUI records diagnostics in bounded local stores by default. Set `log_dir` explicitly to enable a plaintext TUI log for a run:

```bash
codex -c log_dir=./.codex-log
tail -F ./.codex-log/codex-tui.log
```

The non-interactive mode (`codex exec`) defaults to `RUST_LOG=error`, but messages are printed inline, so there is no need to monitor a separate file.

See the Rust documentation on [`RUST_LOG`](https://docs.rs/env_logger/latest/env_logger/#enabling-logging) for more information on the configuration options.
