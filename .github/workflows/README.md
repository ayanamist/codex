# Fork build and release workflow

Scope: `ayanamist/codex`, reviewed on 2026-11-10 against workspace version
`0.167.0` and the accompanying fork changes.
Keywords: GitHub Actions, fork, upstream package, release, voice, version.

Only [`rust-release.yml`](rust-release.yml) remains. Pushing to `fork-release`
automatically selects a tag such as `rust-v0.167.0-ayanamist.1`, builds the
fork's `codex` entrypoint for Linux musl, macOS, and Windows on x86_64 and ARM64,
and publishes a stable release. Manual tag creation is unnecessary. A manual
`workflow_dispatch` on `fork-release` provides a recovery entry point.

The next revision is allocated from existing fork tags for the same upstream
base, and a new base starts at revision 1. A retry reuses the tag already
reserved for that commit. Published commits and obsolete queued push commits
are skipped. The workflow serializes allocation through publication and passes
the selected tag to its later jobs directly, using the built-in `GITHUB_TOKEN`.

The workflow verifies that the corresponding `openai/codex` stable release
exists and its tag commit is an ancestor of the fork commit. It downloads each
platform's official package and verifies the archive checksum, package identity,
voice resource inventory, and upstream voice commit before building. It uses
that package's bwrap digest when compiling Linux Codex and passes the upstream
voice commit separately from the actual fork build commit.

Only `codex-cli --bin codex` is built. Code-mode host, exec-server, voice helper,
native voice runtime, ripgrep, and platform sandbox helpers are reused from the
pinned upstream package. Packaging verifies that reused file contents are
unchanged. V8, lint tools, and separate app-server binaries are not built here.

The fork version is written to Cargo.toml and workspace Cargo.lock entries in
the CI checkout. The integration branch keeps the original upstream version,
reducing merge conflicts. Installers, startup/doctor update checks, and daemon
installation recognize numbered fork releases as stable. See
[release management](../../docs/fork/release-management.md) for the release
procedure, metadata contract, source evidence, and verification commands.

The release publishes six `codex-package-<target>.tar.gz` files,
`codex-package_SHA256SUMS`, the fork's `install.sh` and `install.ps1`, and
`config-schema.json`. A first release can become `latest`; an older upstream
base/revision cannot replace a newer `latest`. Published releases cannot be
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
python3 -m unittest discover -s .github/scripts -p test_releases.py
python3 scripts/install/test_install_sh.py
git diff --check
```

No workflow run or publication was triggered locally. A six-platform Actions run
and platform installation remain separate verification. Branch protection may
still reference removed checks and requires a repository settings change if so.
