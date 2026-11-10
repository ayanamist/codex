# Fork build and release workflow

Scope: `ayanamist/codex`, reviewed on 2026-11-10 against workspace version
`0.167.0` and the accompanying fork changes.
Keywords: GitHub Actions, fork, upstream package, release, voice, version, glibc,
GNU, Windows, MAX_PATH, Cargo, cache, timings, commit hash, SemVer suffix,
paths-ignore.

Only [`rust-release.yml`](rust-release.yml) remains. Pushing to `fork-release`
automatically selects a tag such as `rust-v0.167.0-fork.5d0840ed`, builds the
fork's `codex` entrypoint for Linux GNU/glibc, macOS, and Windows on x86_64 and ARM64,
and publishes a stable release. Manual tag creation is unnecessary. A manual
`workflow_dispatch` on `fork-release` provides a recovery entry point.

The suffix contains the first eight source commit characters, with the full SHA
retained in package metadata and linked release notes. A retry reuses the tag already
reserved for that commit. Published commits and obsolete queued push commits
are skipped. A later documentation-only push does not supersede a pending code
release. The workflow serializes allocation through publication and passes
the selected tag to its later jobs directly, using the built-in `GITHUB_TOKEN`.

Pushes changing only `docs/**` or `.md`, `.mdx`, `.rst`, `.adoc`, and `.mmd` files
are ignored. A push that also changes code still runs; manual dispatch remains
available. The resolver uses the same path exclusions when deciding whether a
newer branch head has superseded a queued code release.

The workflow verifies that the corresponding `openai/codex` stable release
exists and its tag commit is an ancestor of the fork commit. It downloads each
platform's official package (the same-architecture musl package for Linux) and verifies the archive checksum, package identity,
voice resource inventory, and upstream voice commit before building. It uses
that package's bwrap digest when compiling Linux Codex and passes the upstream
voice commit separately from the actual fork build commit.

Only `codex-cli --bin codex` is built. Code-mode host, exec-server, voice helper,
native voice runtime, ripgrep, and platform sandbox helpers are reused from the
pinned upstream package. Packaging verifies that reused file contents are
unchanged. V8, lint tools, and separate app-server binaries are not built here.

Windows jobs use a short Cargo home at the workspace drive root and enable Git
long paths before dependency resolution. Cargo still checks out the pinned V8
source patch while resolving the workspace, even though the CLI does not compile
V8. Without this setup, both Windows jobs in run `42757196810` failed on an ICU
snapshot filename exceeding the Windows path limit.

Each target caches Cargo registry/git data and compiled third-party crates with
`Swatinem/rust-cache`, pinned to v2.9.3's commit. Cache identity includes the
runner/target, Rust/compiler environment, manifests, and lockfile. Restoration
precedes fork version stamping; workspace crates are rebuilt for the new version
and commit. Successful jobs save the cache. Cargo HTML timings are retained as
separate `rust-build-timings-*` artifacts for seven days, outside the release's
`codex-*` download pattern. Gzipped packages upload without redundant ZIP
compression. See the [diagnosis, baseline, and cache limits](../../docs/fork/release-management.md#windows-dependency-checkout-and-build-caching).
The measured Intel macOS cold job took 178 min 39 s. Its timeout is 240 minutes
to leave room for cache saving and build variance; other targets keep 180 minutes.
Release optimization settings are retained.

Linux CLI builds use Ubuntu 22.04 runners (glibc 2.35) to support glibc 2.38
and newer. GNU output metadata records the upstream musl resource target
separately. Before upload, every packaged ELF file is checked for GLIBC imports
above 2.38, including the reused voice runtime and helpers. The Unix installer
selects the GNU archives. See the [compatibility contract](../../docs/fork/release-management.md#linux-glibc-238-compatibility)
for evidence and runtime verification limits.

The fork version is written to Cargo.toml and workspace Cargo.lock entries in
the CI checkout. The integration branch keeps the original upstream version,
reducing merge conflicts. Installers, startup/doctor update checks, and daemon
installation accept arbitrary legal SemVer suffixes, with no hash-length check.
Generated versions use `fork.<eight characters>`; historical numbered releases
remain supported. GitHub Release flags determine the stable channel. See
[release management](../../docs/fork/release-management.md) for the release
procedure, metadata contract, source evidence, and verification commands.

The release publishes six `codex-package-<target>.tar.gz` files,
`codex-package_SHA256SUMS`, the fork's `install.sh` and `install.ps1`, and
`config-schema.json`. A first release can become `latest`; an older upstream
base cannot replace a newer `latest`, and GitHub commit comparison prevents a
behind or diverged source commit from replacing it. Hashes are never ordered
lexically. Published releases cannot be
overwritten; failed drafts can be retried.

The new macOS entrypoint uses an ad hoc signature; the Windows entrypoint is
not Authenticode signed. Reused upstream binary signatures are preserved. No
OpenAI signing credentials, BuildBuddy, custom runners, npm, PyPI, R2, WinGet,
DMG publication, or website deployment are required. PR/post-merge CI, test
suites, lint, and Issue/PR automation remain removed. The workflow's version and
resource checks are release integrity checks.

Local validation:

```sh
actionlint -oneline .github/workflows/rust-release.yml
python3 -m unittest discover -s .github/scripts -p test_fork_release.py
python3 -m unittest discover -s .github/scripts -p test_check_linux_glibc.py
python3 -m unittest discover -s .github/scripts -p test_releases.py
python3 scripts/install/test_install_sh.py
git diff --check
```

No workflow run or publication was triggered locally. Windows checkout and warm
cache behavior with this change still require an Actions run; platform
installation remains separate verification. Branch protection may
still reference removed checks and requires a repository settings change if so.
