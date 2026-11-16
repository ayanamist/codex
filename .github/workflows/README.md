# Fork 发布工作流

范围：`ayanamist/codex`；核对日期：2026-11-16；工作区版本：`0.169.0`。
关键词：GitHub Actions、release、workflow_dispatch、latest、三平台。

| 平台 | 工作流 |
| --- | --- |
| Linux x64 GNU | [rust-release-linux.yml](rust-release-linux.yml) |
| macOS ARM64 | [rust-release-macos.yml](rust-release-macos.yml) |
| Windows x64 MSVC | [rust-release-windows.yml](rust-release-windows.yml) |

三个工作流独立完成解析、构建和上传，公共步骤变更必须同步到三个文件。
向 `fork-release` 推送代码触发预发布；纯文档推送被路径过滤忽略。
只修改某个平台的工作流时，不触发另外两个平台；过时提交检查也使用相同的排除规则。

失败时，在对应工作流选择 **Re-run failed jobs**；也可以在 `fork-release` 上使用
**Run workflow** 手动运行。当前没有编译缓存测量开关，工作流不使用 sccache。

Linux 和 Windows 在同一构建中生成 CLI 和 executor。
macOS 通过两个 matrix job 分别构建，两者共享 rust-cache，由 CLI job 保存缓存；
签名后的可执行文件作为一天有效的 artifact 传给 package job，由它统一打包发布。

各平台独立上传相同 tag 的资产。发布保持 prerelease，单个平台失败时可以补跑。
三个包齐全后仍需维护者手动确认并晋升稳定版：

```sh
gh release edit TAG --repo ayanamist/codex --prerelease=false --latest
```

将 `TAG` 替换成已检查的发布 tag。自动流程不会晋升 `latest`，
默认安装器继续使用此前的稳定版；预发布版本可以显式指定安装。

版本、上游包校验、helper 复用、缓存和验证入口见
[构建与发布维护参考](../../docs/fork/release-management.md)。
面向使用者的安装与更新说明见 [中文使用手册](../../docs/install.md)。
