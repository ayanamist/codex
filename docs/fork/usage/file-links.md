# 对话文件链接

适用范围为本 fork 的 Codex CLI TUI。2026-11-21 根据工作区版本 `0.171.0` 的实现整理。

对话中的 Markdown 文件引用会显示绝对路径和已有的行列号。相对路径以该条消息所属工作目录为基准。缺少工作目录时保留原路径。内置文档查看器可用时，点击链接仍会打开内置查看器。

如果希望交给宿主编辑器，在 `~/.codex/config.toml` 的 `[features]` 段设置 `tui_workspace = false`。这也会关闭工作区侧栏。也可以临时覆盖这项配置。

```bash
codex -c 'features.tui_workspace=false'
```

本地工作区默认根据 `TERM_PROGRAM` 识别编辑器。支持的值为 `vscode`、`vscode-insiders`、`cursor`、`windsurf` 和 `zed`。可在集成终端运行 `printenv TERM_PROGRAM` 核对实际值。显式配置 `file_opener` 会覆盖自动检测。设置 `file_opener = "none"` 可关闭 Codex 生成的编辑器 URI，路径仍可复制或交给终端自己的路径识别。

编辑器 URI 由系统或终端交给对应编辑器，目标窗口由编辑器选择。如果终端中间层改写了 `TERM_PROGRAM`，且 Codex 无法识别编辑器，就只显示路径。远端工作区和 SSH 终端保留路径和可用的内置预览，避免把远端路径交给本机编辑器。

[配置定义](../../../codex-rs/config/src/types.rs) · [链接处理](../../../codex-rs/tui/src/terminal_hyperlinks.rs) · [Zed URI 参考提交](https://github.com/rbright/codex/commit/15e2cee08c95bd4a5343e177480924817f4d1814)

## 验证

Linux 远端构建环境的 425 项定向测试全部通过，覆盖流式与完成态渲染、绝对路径复制、内置预览、语音转录文件链接、转录浮层、编辑器选择和 URI 编码。实际桌面编辑器的窗口选择需要在对应集成终端中核对。

```bash
python3 .cache/remote-dev/remote-dev.py test --offline -p codex-tui --lib \
  -E 'test(markdown) | test(terminal_hyperlinks) | test(file_link) | test(document_link) | test(file_citation) | test(spoken_artifacts) | test(pager_overlay)'
```
