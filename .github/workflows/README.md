# Fork 发布工作流

范围：`ayanamist/codex`；核对日期：2026-11-20；工作区版本：`0.171.0`。
关键词：GitHub Actions、release、workflow_dispatch、latest、三平台。

| 平台 | 工作流 |
| --- | --- |
| Linux x64 GNU | [rust-release-linux.yml](rust-release-linux.yml) |
| macOS ARM64 | [rust-release-macos.yml](rust-release-macos.yml) |
| Windows x64 MSVC | [rust-release-windows.yml](rust-release-windows.yml) |

三个工作流独立完成解析、构建和上传，公共步骤变更必须同步到三个文件。
向 `fork-release` 推送代码触发预发布；纯文档推送被路径过滤忽略。
只修改某个平台的工作流时，不触发另外两个平台；过时提交检查也使用相同的排除规则。

三个工作流从 `codex-rs/rust-toolchain.toml` 读取 Rust 版本。本次上游标签将其更新为
`1.99.1`。上游 Bazel 发布矩阵和 GCS 缓存仅对 `openai/codex` 的受保护标签启用，
fork 继续使用 Cargo 构建。可使用 `actionlint .github/workflows/rust-release-{linux,macos,windows}.yml`
检查三个工作流。

失败时，在对应工作流选择 **Re-run failed jobs**；也可以在 `fork-release` 上使用
**Run workflow** 手动运行。当前没有编译缓存测量开关，工作流不使用 sccache。

Linux 和 Windows 在同一构建中生成 CLI 和 executor。
macOS 通过两个 matrix job 分别构建，两者共享 rust-cache，由 CLI job 保存缓存；
签名后的可执行文件作为一天有效的 artifact 传给 package job，由它统一打包发布。

各平台独立上传相同 tag 的资产，首个平台创建 prerelease。
Linux 和 Windows 在构建、打包和检查通过后的发布步骤传入 `--promote-when-ready`：
同一 tag 的两个平台包均存在、共享校验清单成功上传且包集合稳定后，自动移除 prerelease
并设为 `latest`。就绪依据是对应 release 的包资产，不需要等待 macOS；
macOS 随后独立补包并更新校验清单，不修改稳定通道。

缺少 Linux 或 Windows 包时保持 prerelease；失败平台补跑成功后可完成晋升。
默认安装器在晋升后使用新稳定版；晋升前仍可显式指定预发布版本安装。

版本、上游包校验、helper 复用、缓存和验证入口见
[构建与发布维护参考](../../docs/fork/release-management.md)。
面向使用者的安装与更新说明见 [中文使用手册](../../docs/install.md)。
