# Fork notes

- [Fork release management](release-management.md): rebuilding only the Codex
  entrypoint, reusing pinned upstream helpers, V8 and voice constraints, version
  sources, automatic commit-based releases on code pushes, documentation-only
  push filtering, and Linux GNU builds
  compatible with glibc 2.38; Windows long-path checkout diagnosis, Cargo
  dependency caching, cold-build evidence, build timings, and Rust toolchain
  input warning diagnosis. Keywords: fork,
  upstream tag, release, automatic tag, version, V8, voice, installer, glibc,
  GNU, Windows, MAX_PATH, Cargo, cache, timings, Rust, toolchain, dtolnay,
  commit hash, SemVer suffix, paths-ignore.
  Implemented: 2026-11-10.
- [Build and GitHub Release workflows](../../.github/workflows/README.md):
  retained build, packaging, and GitHub Release automation; removed CI,
  tests, Issue/PR automation, and external publication. Keywords: GitHub Actions,
  release, tag, npm, PyPI, R2. Reviewed: 2026-11-10.
- [CLI update sources](updates.md): standalone CLI and daemon updates through
  `ayanamist/codex` GitHub Releases; installer behavior, release requirements,
  limitations, and verification. Keywords: `codex update`, fork, GitHub Releases,
  installer, Homebrew, npm, pnpm, Bun, Vite+, version cache. Reviewed: 2026-11-10.
