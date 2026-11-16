# 构建与发布维护参考

范围：`ayanamist/codex` 的三平台独立构建、打包与 GitHub Releases 分发。
核对日期：2026-11-16；工作区版本：`0.169.0`。
关键词：release、GitHub Actions、版本、helper、glibc、V8、rust-cache、prerelease。
安装与更新操作见 [中文使用手册](../install.md)。

## 工作流与发布入口

三个工作流各自完成 resolve、build、upload，互不等待另一平台构建成功：

| 平台 | 工作流 | Runner | 构建超时 |
| --- | --- | --- | --- |
| Linux x64 GNU | [`rust-release-linux.yml`](../../.github/workflows/rust-release-linux.yml) | `ubuntu-22.04` | 180 分钟 |
| macOS ARM64 | [`rust-release-macos.yml`](../../.github/workflows/rust-release-macos.yml) | `macos-15` | 每个构建 300 分钟；打包 60 分钟 |
| Windows x64 MSVC | [`rust-release-windows.yml`](../../.github/workflows/rust-release-windows.yml) | `windows-2025` | 180 分钟 |

向 `fork-release` 推送代码会触发发布。仅修改 `docs/**` 或 `.md`、`.mdx`、`.rst`、
`.adoc`、`.mmd` 文件的推送被忽略。手动 `workflow_dispatch` 不受路径过滤影响。
各平台还会排除另外两个平台的工作流文件；resolve 的 `--ignored-path`
与路径过滤使用相同的排除规则，避免其他平台的单独调整使当前发布过时。
同一平台串行运行；一个平台失败不会取消其他平台，也不妨碍成功平台保存缓存。
公共构建、版本和打包步骤的修改必须同步到三个工作流。

集成上游时，合并已发布的准确稳定 tag，保留集成分支中的上游源码和 manifest。
无需手工修改 Cargo 版本或创建 fork tag。推送前审查预期变更；
工作流仅处理已推送内容。

失败恢复可在对应平台的 Actions 页面选择 **Re-run failed jobs**，
或在 `fork-release` 上选择 **Run workflow**。
当前没有编译缓存测量开关，工作流不使用 sccache。

## 版本与发布通道

[`fork_release.py`](../../.github/scripts/fork_release.py) 从原始 workspace 版本解析上游稳定版本，
确认 `openai/codex` 对应发布存在，且上游 tag commit 是 fork commit 的祖先。
生成版本为 `<上游版本>-fork.<序号>.g<源码提交前八位>`，例如
`0.169.0-fork.6.g661ed353`；tag 为 `rust-v<版本>`。
序号通过 `git rev-list --ancestry-path --count <upstreamCommit>..<forkCommit>`
计算，统计当前提交祖先中属于该上游版本后代的全部提交，包含合并进来的旁支历史。
在同一上游版本内，后代提交的计数严格增加，即使已发布历史位于合并提交的第二父链也成立。
只沿第一父链计数不满足这个条件：普通 `git pull` 合并就可能让序号从 6 降到 3，
导致更新提示失效；对应回归测试用真实 Git 仓库验证了这一情形。
合并旁支和纯文档提交可能让已发布序号跳号。同一源码在三平台和重跑中得到相同版本，
不依赖 Actions 运行编号或发布完成时间。该顺序依赖提交祖先关系，历史重写需另行处理。
完整源码提交保存在 tag 目标和包元数据中；短哈希碰撞时必须失败。
`g` 前缀让全数字及以零开头的短哈希仍然是合法 SemVer 标识。

三个平台为同一源码计算相同 tag，允许兄弟工作流先创建该 tag。
过时的排队代码提交会跳过；较新的纯文档提交不使仍待发布的代码失效。
重跑复用同一提交的 tag；缺少的平台包可补传。

首个平台创建非 latest 的 prerelease，随后各平台通过 `--clobber` 上传本平台包、
安装器，并根据远端资产摘要重新生成 `codex-package_SHA256SUMS`。
发布说明在创建时写入，后续平台不覆盖。
三个目标包齐全后仍保持 prerelease，不自动晋升 `latest`。
自动发布不再执行相对于当前 latest 的版本和提交祖先检查。
维护者检查包完整性及目标版本后，可以显式晋升：

```sh
gh release edit TAG --repo ayanamist/codex --prerelease=false --latest
```

将 `TAG` 替换成实际发布 tag。晋升前，默认安装入口继续提供先前的稳定版；
预发布版本需要通过安装器显式指定版本安装。

## 构建与包内容

发布流程只重新编译 CLI 和独立 executor 及其依赖。
Linux 和 Windows 在同一次构建中选择两个入口：

```sh
cargo build --locked --release --timings \
  -p codex-cli -p codex-exec-server-cli \
  --bin codex --bin codex-exec-server --target "$TARGET"
```

此命令由工作流在准备完成的构建副本中执行。开发验证使用约定的构建环境。

macOS 通过两个 matrix job 分别构建 `codex` 和 `codex-exec-server`。
两者共享同一个 rust-cache key，仅 `codex` job 保存缓存。
每个入口 strip、ad hoc 签名后上传为一天有效的 artifact，
后续 package job 下载两个入口，重新准备上游包，再组装、检查和发布。

prepare 阶段下载并校验准确上游包、校验清单、包身份、voice 清单及 runtime commit。
assemble 阶段同时替换 `bin/codex` 和 `bin/codex-exec-server`，并检查两者的 fork 版本。
code-mode host、voice helper/runtime、ripgrep、bwrap 和 Windows 沙箱辅助程序复用上游内容，
通过摘要检查保持原字节。没有单独的 app-server、V8、npm、PyPI 或 DMG 发布。

| 元数据 | 契约 |
| --- | --- |
| `codex-package.json` | fork 版本、实际 `buildCommit`、`upstreamTag` 和 `upstreamCommit` |
| voice manifest | `buildCommit` 保留上游 helper 提交；`appBuildCommit`、`appVersion` 标记 fork；更新受替换入口的清单摘要 |
| `fork-build.json` | fork/上游身份、CLI/executor 摘要、`rebuiltBinaries` 及复用上游文件的原始校验值 |

Unix 新入口会 strip；macOS 做 ad hoc 签名，未做 Apple 开发者公证。
Windows 新入口没有 Authenticode 签名；复用的上游文件保留原签名字节。

## 辅助程序兼容性

`STABLE_GIT_COMMIT` 记录实际 fork 提交。
编译期 `CODEX_VOICE_HELPER_COMMIT` 只用于 voice 握手，使客户端能连接准确上游 helper。
未设置时仍采用原有同构建握手；运行时环境变量不能改写该编译期值。
上游 runtime 的 source commit 不能被重新标记为 fork。

复用文件摘要一致只证明字节来源，不能证明上游 helper 包含 fork 源码变化。
修改 code-mode、voice、沙箱协议或 helper 依赖后，需要检查复用兼容性；
目前没有对所有复用 helper 实施通用的传递依赖变更阻断检查。
完整包的代表性运行行为需另行验证。

## Linux 兼容与资源身份

Linux 包目标为 `x86_64-unknown-linux-gnu`，要求 glibc 2.38 或更新。
复用资源来自同架构上游 musl 包，元数据区分 fork 输出目标与上游资源目标。
上传前对包中所有 ELF 文件检查 GLIBC 导入，不允许超过 2.38。

[`bundled_bwrap.rs`](../../codex-rs/linux-sandbox/src/bundled_bwrap.rs)
验证的 bwrap 摘要必须来自实际下载资源；prepare 在编译前输出 `CODEX_BWRAP_SHA256`。
打包后不能再次 strip 或改写该 bwrap。
静态符号上限检查不能替代目标系统上的安装与运行验证。

## 构建副本中的版本适配

[`prepare_fork_sources.py`](../../.github/scripts/prepare_fork_sources.py)
只在一次性构建副本中将内部 Cargo 包身份规范为 `0.0.0`，并适配上游版本读取点。
集成分支保留原有消费者源码、Cargo.toml 和 Cargo.lock。
最终可执行入口通过 `CODEX_RELEASE_VERSION` 嵌入发布版本，库通过
[`codex-build-info`](../../codex-rs/build-info/src/lib.rs) 的运行时接口读取。

扫描器需自动覆盖新增文件，遇到不支持的版本读取语法时在写入前拒绝处理。
显式使用 UTF-8，支持 LF/CRLF；适配报告保存在构建指标 artifact。
上游 main 的开发版本和稳定发布 tag 的版本各有来源，不能用 main 的 `0.0.0` 推断发布基础版本。

## V8 源准备与缓存

[`prepare_rusty_v8_source.py`](../../.github/scripts/prepare_rusty_v8_source.py)
在 Cargo 和缓存恢复之前准备准确 rusty_v8 提交的根源码快照，避免下载 V8/ICU 子模块。
pin 位于 [`rusty_v8_152_2_0_source.json`](../../third_party/v8/rusty_v8_152_2_0_source.json)；
脚本核对 manifest、lockfile 和摘要，
在构建副本追加目录源替换，保留原 git 源身份和其他 Cargo 配置。
未知 revision、摘要不匹配或冲突配置必须失败，不能自动退回完整 clone。
快照只适用于预编译原生库模式，强制 `V8_FROM_SOURCE=0`，不能用于完整 C++ 源码构建。

复用上游 code-mode host 不等同于重新编译 V8。
若未来需要重建 host，可以研究复用校验后的原生库及 binding，但必须另行确认 Rust ABI、
feature、目标平台和 pin 的兼容性。

Cargo 依赖及第三方编译产物通过 rust-cache 保留；显式 key 包含与版本无关的根构建设置指纹。
内部包身份在构建副本中保持稳定；工作流不使用 sccache，也不保留双次构建测量模式。
三个工作流都设置 `cache-workspace-crates: "false"`，不保存工作区 crate 的编译产物；
即使第三方依赖全部命中，内部 crate 仍会重新编译，可执行文件仍需最终链接。
判断是否复用应同时检查恢复日志和 Cargo 实际编译列表：`Cache restored successfully`
表示恢复完成；`full match: false` 仅表示通过 restore key 前缀恢复了旧依赖指纹的缓存，
不表示恢复失败。该行为见固定版本的 [rust-cache 恢复逻辑](https://github.com/Swatinem/rust-cache/blob/d1527c8f67ef9af357290475d4af4b0fab8f12e0/src/restore.ts)。
缓存仍会受编译器、依赖、编译参数和存储淘汰影响，不能保证暖构建时长。
Windows 使用短 Cargo home，并在依赖解析前启用 Git longpaths。

`rust-build-timings-*` artifact 保留 Cargo HTML timings 和源适配报告，保存七天。
macOS 分别保存两个入口的 timing artifact；不再生成 sccache JSON 或暖构建测量 artifact。

## 安装器与更新契约

[`install.sh`](../../scripts/install/install.sh) 和
[`install.ps1`](../../scripts/install/install.ps1) 从本 fork 的 GitHub Releases
解析 latest 或指定版本，并验证 SHA-256；默认请求失败就停止，不回退官方分发。
继承的 `CODEX_INSTALLER_USE_RELEASES_OPENAI_COM` 不能切换到官方镜像。
安装器接受合法 SemVer 后缀，也保留历史编号版本支持。
`latest` 查询只选择稳定发布，不会自动选择当前流程生成的 prerelease。

共享校验清单 `codex-package_SHA256SUMS` 必须在所有发布平台固定输出 UTF-8、LF 换行，
不使用 Windows 文本模式默认的 CRLF。Unix 安装器同时接受 LF 和 CRLF，解析时只移除行尾
`\r`，仍严格匹配附件名、64 位十六进制摘要并校验下载内容。
2026-11-16 核对 `rust-v0.169.0-fork.0ff7a389` 的实际附件确认：Windows 发布后清单为 CRLF，
旧 Unix 安装器会将行尾 `\r` 计入文件名并报找不到摘要。对应回归测试覆盖 Windows 文本模式
下发布清单的原始字节，以及 Linux/macOS 平台选择时读取 CRLF 清单；平台选择测试使用模拟包，
不代表已经执行原生 macOS 或 Windows 安装。

`.gitattributes` 中的 `scripts/install/install.sh text eol=lf`（提交 `51c9b2f549`）
只约束 Git 检出安装脚本的换行，不能约束 Python 在发布时生成的清单。该修复在本次故障版本中
仍然存在：脚本本身为 LF，清单为 CRLF。各平台都会覆盖共享清单，其换行因此取决于最后上传
平台；必须在生成端显式指定换行。清单回归测试需比较原始字节，`read_text().splitlines()`
会消除 LF/CRLF 差异，无法检查这一契约。

独立安装的 CLI `codex update` 和托管 daemon 使用 fork 安装器。
官方 Homebrew、npm、pnpm、Bun、Vite+ 自动更新被拒绝，需要迁移到独立安装。
debug 构建拒绝 update，未知安装布局要求手工更新。
启动和 doctor 检查均查询 fork；启动版本缓存位于 `$CODEX_HOME/version.json`，
后台刷新间隔为 20 小时。启动和 doctor 共用 `codex-build-info::is_newer_release`：
先比较上游基础版本，再比较同一基础版本内的数字序号，短哈希只用于追溯。
同一序号的不同哈希不表示先后；低序号或旧哈希格式缓存不会提示新格式安装回退。
同一基础版本内，新格式高于历史 `fork.<哈希>` 和 `ayanamist.<编号>`，支持单向迁移；
跨基础版本仍按基础版本比较。缓存结构和 20 小时周期保持上游设计，
没有新增与安装版本绑定的缓存字段。此规则适用于新格式安装；旧版 CLI 需先升级才能使用新比较逻辑。
`codex update` 不使用该缓存。
debug 和 `0.0.0` 源码构建不进行启动更新检查。
没有用于指定 GitHub 仓库或安装器 URL 的 config.toml 设置。

## 证据与核对命令

当前事实以三个工作流、`fork_release.py`、源准备脚本、安装器和对应测试为依据。
本页不保留历史运行耗时、失败流水线和逐次验证结果。

只读定位与链接核对可以本地执行：

```sh
rg -n 'paths-ignore|workflow_dispatch|timeout-minutes|ignored-path|matrix:' .github/workflows/rust-release-*.yml
rg -n '^def (resolve|prepare|assemble|publish)' .github/scripts/fork_release.py
git diff --check
```

在约定的构建环境中，从仓库根目录执行相关测试，例如：

```sh
python3 -m unittest discover -s .github/scripts -p test_fork_release.py
python3 -m unittest discover -s .github/scripts -p test_prepare_fork_sources.py
python3 -m unittest discover -s .github/scripts -p test_prepare_rusty_v8_source.py
python3 -m unittest discover -s .github/scripts -p test_check_linux_glibc.py
python3 scripts/install/test_install_sh.py
cargo nextest run --manifest-path codex-rs/Cargo.toml -p codex-build-info --lib
```

这些命令不代表本次文档整理已执行测试或发布。三平台安装、签名体验、完整包运行和
缓存性能需要各自的实测。
