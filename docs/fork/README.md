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
  Compiler-cache diagnosis: 2026-11-11, run `42941045713`; version-only root
  manifest changes invalidate all three caches, Cargo timing evidence identifies
  large workspace/bin tasks, and sccache coverage is limited by executable
  linking and per-release workspace version stamping. Keywords: sccache,
  ThinLTO, restore key, compiler cache, package identity.
  Implemented: 2026-11-11, version-independent build-settings fingerprint,
  pinned sccache and manual benchmark mode without tag allocation/publication;
  remote library probe confirms internal cache misses after version-only
  stamping. Upstream main's `0.0.0` differs from the release-tag version.
  Build-copy adapter implemented: the integration branch retains upstream
  consumer sources and manifests; a guarded scanner adapts new version reads
  and normalizes internal identities to `0.0.0` only while building. Executable
  stamps feed a common runtime interface; a new-stamp probe preserves all
  49 library cache hits. Keywords: source preparation, tokenizer, upstream
  merges, `application_version`, `CODEX_RELEASE_VERSION`, executable stamp.
  Windows follow-up: run `42972181582` exposed implicit CP1252 source decoding;
  the adapter now uses explicit UTF-8 I/O, with LF/CRLF and full-workspace
  encoding regression coverage. Keywords: UTF-8, CP1252, UnicodeDecodeError.
  macOS timeout follow-up: 2026-11-12, run `43135737205` hit its three-hour
  job limit after a dependency-cache miss and unexpected sccache server exit;
  the macOS ARM64 budget is now 300 minutes, pending Actions verification.
  Keywords: macOS ARM64, timeout, cold build, sccache server exit.
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
