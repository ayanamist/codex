# Fork release management

Scope: the `ayanamist/codex` fork on `fork-release`, investigated and implemented
on 2026-11-10 against `11f857b31e`, upstream `rust-v0.167.0`, workspace version
`0.167.0`, plus the accompanying uncommitted fork release changes.
Keywords: fork, release, upstream tag, version, helpers, V8, voice, installer.

## Release procedure

Keep `fork-release` as the integration branch. After upstream publishes a stable
release, fetch its tags and merge the exact release tag. Commit local feature
changes normally. Pushing this branch automatically allocates a fork version,
creates its tag, builds the six platform packages, and publishes a stable
GitHub Release. A push containing several commits releases the branch tip.
No manual tag or Cargo version edit is needed.

The fork tag combines the upstream version and a positive fork revision:

| Upstream base | Fork version | Fork release tag |
| --- | --- | --- |
| `0.167.0` | `0.167.0-ayanamist.1` | `rust-v0.167.0-ayanamist.1` |
| `0.167.0` | `0.167.0-ayanamist.2` | `rust-v0.167.0-ayanamist.2` |
| `0.168.0` | `0.168.0-ayanamist.1` | `rust-v0.168.0-ayanamist.1` |

After committing and reviewing the intended source and workflow changes, an
example upstream update is:

```sh
git switch fork-release
git fetch upstream --tags
git merge rust-v0.167.0
# Commit any remaining intended fork changes before pushing.
git push origin fork-release
```

These commands are a documented procedure, not actions performed during this
change. The workflow finds the largest existing fork tag revision for the same
upstream base and reserves the next number. A new base starts at revision 1.
The tag is a lightweight reference to the exact checked-out commit. Imported
upstream tags remain unchanged and tag pushes do not trigger this workflow.

Allocation and publication are serialized across workflow runs. A queued run
whose source commit is no longer the tip of `fork-release` skips publication.
The active run is allowed to finish. With GitHub's default single pending slot,
newer pushes can replace an older waiting run; this branch tracks the latest
pushed state rather than promising a separate release for every intermediate
push. See [workflow concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
The same commit reuses an existing reserved tag, including a tag whose build
failed or whose release is still a draft. If the commit has already been
published, the build and release jobs are skipped instead of incrementing the
revision again. Number comparison is numeric, so `.10` follows `.9`.

To recover a failed run, use **Re-run failed jobs** on that Actions run while
the commit is still current. **Run workflow** is also available on the default
`fork-release` branch after this workflow is pushed. A newer push is handled as
a new release rather than resuming the superseded commit. This automation only
sees pushed commits; a local merge without a push cannot trigger GitHub Actions.

The tag is created with the built-in `GITHUB_TOKEN` and the same workflow
continues with the selected tag as a job output. It does not depend on that
token's tag creation triggering another run, which
[GitHub normally suppresses](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).
No additional personal access token or notification integration is required.

The workflow verifies that the base matches the unmodified workspace version,
that the upstream release is stable and published, and that its resolved tag
commit is an ancestor of the fork commit. Merely labeling arbitrary main-branch
code with an older release version is insufficient.

## Build and package contract

The single [release workflow](../../.github/workflows/rust-release.yml) invokes
[`fork_release.py`](../../.github/scripts/fork_release.py) in four stages:

1. `resolve`: identify the exact upstream stable tag/commit and Rust toolchain;
   allocate or resume the automatic fork tag after validation, or skip a
   superseded/already published commit.
2. `prepare`: download `codex-package-<target>.tar.gz` and its official checksum
   manifest from `openai/codex`; verify the archive, package metadata, voice
   inventory, and runtime commit; stamp the full fork version in the isolated
   CI checkout and export build inputs.
3. `assemble`: replace only the package's `bin/codex[.exe]`, update package and
   voice metadata, verify reused upstream files are unchanged, and create the
   new gzip archive.
4. `publish`: require all six platform packages, generate checksums, add the
   fork installers and config schema, upload to a draft, and publish it as a
   stable GitHub Release. Published releases cannot be overwritten. A failed
   draft can be retried. The first release handles an absent latest channel;
   API failures other than HTTP 404 remain failures.

Linux musl, macOS, and Windows packages are built for x86_64 and ARM64 using
standard GitHub-hosted runners. Cargo builds only:

```sh
cargo build --locked --release -p codex-cli --bin codex --target "$TARGET"
```

The workflow preserves code-mode host, exec-server, voice helper/runtime,
ripgrep, bwrap, and Windows sandbox helper contents from the corresponding
upstream package. It does not publish separate app-server bundles, V8, lint
tools, npm packages, Python wheels, or DMGs. App-server and executor library
code required by the CLI still compiles into the `codex` executable.

The [package layout](../../scripts/codex_package/layout.py) and
[prebuilt-input flags](../../scripts/codex_package/cli.py) already support the
separation between an entrypoint and helpers. The fork script overlays the
complete official package so resources outside the basic layout are retained.

On Linux, [`bundled_bwrap.rs`](../../codex-rs/linux-sandbox/src/bundled_bwrap.rs)
checks the bundled bwrap against a digest embedded in Codex. `prepare` computes
`CODEX_BWRAP_SHA256` from the exact downloaded resource before compilation.
No later operation strips or changes bwrap.

## Voice handshake and provenance

The [voice connection](../../codex-rs/realtime-webrtc/src/client.rs) sends
`Hello { protocol: 1, build_commit }`. The
[helper](../../codex-rs/voice-host/src/main.rs) compares it with the exact
`STABLE_GIT_COMMIT` string embedded in that helper, then replies `Ready`.
It does not compute the client executable's digest or reconstruct a Git commit.
Its `--build-commit` argument prints the expected value. Wrong commit strings
and protocol versions are rejected by existing lifecycle tests.

The fork introduces a compile-time override at the connection boundary:

| Build input | Meaning |
| --- | --- |
| `STABLE_GIT_COMMIT` | Actual fork source commit, used by the main binary's build information and build ID |
| `CODEX_VOICE_HELPER_COMMIT` | Pinned upstream voice helper commit, used only in the voice handshake |

Without the override, voice keeps the existing same-build behavior. A runtime
environment variable cannot change this compile-time setting.

The upstream [voice assembler](../../third_party/voice/assemble_package.py)
requires app and voice runtime to share a commit. The fork overlay therefore
uses its own explicit combination contract, retaining all original native
files and runtime receipt bytes:

- `codex-package.json` records the full fork version, actual `buildCommit`,
  `upstreamTag`, and `upstreamCommit`.
- `codex-resources/voice/manifest.json.buildCommit` retains the unchanged
  upstream helper commit; `appBuildCommit` records the actual fork commit;
  `appVersion` records the fork version. The CLI's inventory digest is updated.
- `fork-build.json` records the fork/upstream source identities, entrypoint
  digest, and original checksums of reused upstream files.

[`BuildInfo`](../../codex-rs/build-info/src/lib.rs) continues to report the
actual fork commit. The upstream runtime's `sourceCommit` is never relabeled as
a fork build. Future changes to voice protocol, code-mode/executor protocol,
or sandbox behavior require checking compatibility with the pinned helpers.

## V8 and version sources

V8 is linked by [code-mode-runtime](../../codex-rs/code-mode-runtime/Cargo.toml),
used by the separate [code-mode host](../../codex-rs/code-mode-host/Cargo.toml).
The CLI uses the separate code-mode client and resolves that host through
[`InstallContext`](../../codex-rs/install-context/src/lib.rs). A local manifest
traversal, including normal/build dependencies, all targets and optional
features but excluding dev dependencies, found no V8/runtime/host dependency
path from `codex-cli`. External crate graphs were not traversed. Reusing the
upstream host eliminates rebuilding it and its V8 dependency in this workflow.
Cargo's actual normal/build dependency graph for the Linux CLI was subsequently
checked as well: it contains no V8, code-mode runtime, or code-mode host.
The existing [V8 download action](../../.github/actions/setup-rusty-v8/action.yml)
remains available to source builds that need the host, but is not called here.

Cargo.toml owns the compiled package version. Creating a tag alone does not
change `codex --version`. `prepare` changes the workspace version and all local
workspace package entries/references in Cargo.lock, including implicit workspace
members, only in the CI checkout. It accepts upstream lockfiles whose local
package entries still carry `0.0.0`; registry/git package versions stay unchanged.
The integration branch retains the upstream version to reduce merge conflicts.

The [release validator](../../.github/scripts/releases.py),
[Unix installer](../../scripts/install/install.sh),
[Windows installer](../../scripts/install/install.ps1),
[TUI update check](../../codex-rs/tui/src/update_versions.rs),
[doctor update check](../../codex-rs/cli/src/doctor/updates.rs), and
[daemon package staging](../../codex-rs/app-server-daemon/src/prepare_install.rs)
recognize numbered fork releases. Update comparison orders numeric upstream
versions first and numeric fork revisions second. Older bases/revisions cannot
replace a newer latest release. Although the suffix is a SemVer prerelease
identifier, the workflow explicitly publishes it with GitHub `prerelease=false`.

Do not use four numeric components, which Cargo/SemVer reject, or rely on build
metadata such as `+ayanamist.N` for update precedence. Upstream alpha/beta
handling is retained outside the fork's stable tag trigger.

## Evidence, verification, and limits

The official [0.167.0 release](https://github.com/openai/codex/releases/tag/rust-v0.167.0)
was the latest upstream stable release at the 2026-11-10 inspection. Its resolved
commit was `086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a`; the fork release list was
empty. These are point-in-time observations. Standard runner labels were checked
against [GitHub's runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

Local verification includes the actual Linux x86_64 upstream package: archive
checksum verification, package/voice inventory verification, helper commit
inspection, rejection of a different commit, and acceptance of the pinned one.
The modified Rust client was compiled with the override and successfully
connected to that actual helper with a different app commit, initialized the
packaged GStreamer runtime, and closed it. No microphone/speaker access or
network transport was exercised.

Release resolution was also exercised in an isolated Git checkout against the
official GitHub release API and fetched upstream tag. The version transformation
was checked on a complete source copy using `cargo metadata --offline --locked
--no-deps`; all 171 inherited workspace packages received the fork version.

```sh
actionlint -oneline .github/workflows/rust-release.yml
python3 -m unittest discover -s .github/scripts -p test_fork_release.py
python3 -m unittest discover -s .github/scripts -p test_releases.py
python3 scripts/install/test_install_sh.py
sh -n scripts/install/install.sh
cd codex-rs
cargo test --offline -p codex-build-info -p codex-realtime-webrtc --lib
CODEX_VOICE_HELPER_COMMIT=086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a \
CODEX_TEST_UPSTREAM_VOICE_PACKAGE=/tmp/codex-upstream-overlay-check/package \
  cargo test --offline -p codex-realtime-webrtc --lib \
  pinned_upstream_voice_package_accepts_a_different_app_commit -- --ignored
cargo test --offline -p codex-app-server-daemon --lib numbered_fork_versions_use_the_stable_install_channel
cargo test --offline -p codex-tui --lib update_versions::tests --no-default-features
cargo test --offline -p codex-cli --bin codex doctor::updates::tests::is_newer_compares_plain_semver
cargo tree --offline --locked -p codex-cli --edges normal,build --prefix none --format '{p}'
```

Results on 2026-11-10: the initial implementation passed 9 fork release script tests, 24 existing release script
tests, 18 installer tests, 9 build-info tests, 22 regular voice client tests,
the separately enabled real upstream voice integration test, 10 TUI version
tests, one daemon staging version test, and one CLI doctor version test passed.
Actionlint, shell syntax, documentation links, and whitespace checks passed.
The existing unrelated unused-variable warning in `tui/src/chatwidget/rate_limits.rs`
remains. Test-generated Cargo.lock version changes were restored.

The subsequent automatic-tag update added eight cases, bringing the fork
release suite to 17 passing tests. These cover numeric allocation, revision
reset on a new base, retry/draft reuse, already published commit deduplication,
annotated tags, obsolete pushes, job output propagation, and structured API
request bodies. Actionlint, workflow dependency/output checks, documentation
links, and whitespace checks passed again. Tag creation was mocked in tests;
no live repository tag was created during verification. The repository default
branch was confirmed as `fork-release` through a read-only GitHub API request.

The new macOS entrypoint is stripped and ad hoc signed, without Apple's developer
signing identity or notarization. The new Windows entrypoint is not Authenticode
signed. Reused upstream binaries retain their original signed bytes. No OpenAI
signing credentials, custom runner groups, or BuildBuddy are required. Platform
signing/installation and a complete six-platform Actions build remain unverified.
No commit, tag creation, push, workflow run, or release publication was performed.
