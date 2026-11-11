# Fork notes

- [Project MCP configuration](project-mcp-configuration.md): trusted-project
  `.mcp.json` compatibility, JSONC, variables, headers, nested discovery,
  atomic server replacement and native TOML overrides; plugin JSON loading,
  external-agent import, global CLI writes, and comparison
  with other coding agents' project MCP configuration and compatibility paths;
  upstream PR search, unmerged cwd `mcp.json` patch, TOML-only issue closure,
  pinned Pi adapter/VS Code implementation evidence, and the confirmed
  compatibility target (legacy SSE warns and is skipped).
  Keywords: MCP, `.mcp.json`, `mcpServers`, `mcp_servers`, project, trust,
  migration, plugins, `codex mcp add`, Claude Code, Copilot, Cursor, Pi,
  Gemini CLI, OpenCode, JSONC, headers, environment variables, SSE,
  openai/codex#12718, openai/codex#13056.
  Implemented: 2026-11-11, `0.167.1`.
- [Skill invocation policy compatibility](skill-invocation-policy.md): fall back
  to `SKILL.md` frontmatter when `agents/openai.yaml` leaves invocation unset;
  preserve explicit Codex policy and product restrictions across host and
  executor discovery. Keywords: skills, `disable-model-invocation`,
  `allow_implicit_invocation`, explicit-only, frontmatter, Claude Code,
  openai/codex#29989. Implemented: 2026-11-10.
- [Linux sandbox empty mount targets](sandbox-mount-targets.md): known upstream
  issue, host directory creation, interrupted cleanup, identity-based recovery,
  user data protection, and verification. Keywords: Linux, bubblewrap, bwrap,
  empty directory, `.agents`, `.aws`, `.codex`, `.git`, SIGKILL, inode, cleanup.
  Investigated: 2026-11-10.
- [Fork release management](release-management.md): rebuilding the Codex
  CLI and standalone executor, reusing pinned upstream helpers, V8 and voice
  constraints, version sources, automatic commit-based releases on code pushes, documentation-only
  push filtering, and Linux GNU builds
  compatible with glibc 2.38; Windows long-path checkout diagnosis, Cargo
  dependency caching, cold-build evidence, build timings, and Rust toolchain
  input warning diagnosis; three-platform release scope (Linux/Windows x64,
  macOS ARM64), observed cache eviction, and removal of the large V8 git
  checkout while retaining other git and third-party build artifacts; V8 source
  resolution versus compilation, upstream host reuse, available V8 prebuilt libraries, and the
  source-coverage audit and fix for the standalone executor. Keywords: fork,
  upstream tag, release, automatic tag, version, V8, voice, installer, glibc,
  GNU, Windows, MAX_PATH, Cargo, cache, timings, Rust, toolchain, dtolnay,
  commit hash, SemVer suffix, paths-ignore, platform matrix, cache eviction,
  V8 prebuilt, code-mode host, RUSTY_V8_ARCHIVE,
  helper source coverage, standalone executor, Cargo source replacement,
  V8 source snapshot, submodule downloads. A pinned 405 KB snapshot now avoids
  V8/ICU git checkout; Linux prebuilt V8 execution was verified.
  Implemented: 2026-11-10. Latest upstream integration: 2026-11-11,
  `rust-v0.167.1`; workspace version conflict and isolated release-test fixture.
- [Build and GitHub Release workflows](../../.github/workflows/README.md):
  retained build, packaging, and GitHub Release automation; removed CI,
  tests, Issue/PR automation, and external publication. Keywords: GitHub Actions,
  release, tag, npm, PyPI, R2. Reviewed: 2026-11-10.
- [CLI installation and update sources](updates.md): first-install commands in
  the README and [installation guide](../install.md), supported release targets,
  migration from official packages, standalone CLI and daemon updates through
  `ayanamist/codex` GitHub Releases; installer behavior, release requirements,
  limitations, and verification. Keywords: first install, migration, PATH,
  `codex update`, fork, GitHub Releases, installer, Homebrew, npm, pnpm, Bun,
  Vite+, version cache. Reviewed: 2026-11-11.
