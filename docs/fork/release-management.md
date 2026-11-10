# Fork release management

Scope: the `ayanamist/codex` fork on `fork-release`, investigated and implemented
on 2026-11-10 against `11f857b31e`, upstream `rust-v0.167.0`, workspace version
`0.167.0`, plus the accompanying uncommitted fork release changes.
Linux glibc compatibility was updated on 2026-11-10 against `f146e4071a`,
workspace version `0.167.0`, plus the accompanying changes.
Windows dependency checkout and release caching were updated on 2026-11-10
against `6305206509`, workspace version `0.167.0`, and Actions run `42757196810`.
Documentation-only push filtering and commit-based versions were updated on
2026-11-10 against `5d0840ed69be4451d0a3dba14a26e1a833629b5f` plus local changes.
Keywords: fork, release, upstream tag, version, helpers, V8, voice, installer,
glibc, GNU, Windows, MAX_PATH, Cargo, cache, build timings, commit hash,
SemVer suffix, paths-ignore.

## Release procedure

Keep `fork-release` as the integration branch. After upstream publishes a stable
release, fetch its tags and merge the exact release tag. Commit local feature
changes normally. Pushing this branch automatically allocates a fork version,
creates its tag, builds the six platform packages, and publishes a stable
GitHub Release. A push containing several commits releases the branch tip.
No manual tag or Cargo version edit is needed. Pushes changing only `docs/**`
or files ending in `.md`, `.mdx`, `.rst`, `.adoc`, or `.mmd` do not start the
workflow. Mixed documentation/code pushes still release the branch tip;
`workflow_dispatch` remains available regardless of changed paths. These are
[GitHub path filters](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore),
so GitHub's documented diff limits also apply.

The generated fork tag combines the upstream version and the first eight
lowercase characters of the source commit (the table uses illustrative commits):

| Upstream base | Fork version | Fork release tag |
| --- | --- | --- |
| `0.167.0` | `0.167.0-fork.5d0840ed` | `rust-v0.167.0-fork.5d0840ed` |
| `0.167.0` | `0.167.0-fork.abcdef12` | `rust-v0.167.0-fork.abcdef12` |
| `0.168.0` | `0.168.0-fork.abcdef12` | `rust-v0.168.0-fork.abcdef12` |

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
change. The workflow derives the tag directly from the upstream base and source
commit, without allocating a numeric revision. The complete commit is retained
in the tag target, package metadata, and linked release notes. An existing
eight-character tag must point to the same full commit; a collision fails
explicitly rather than reusing another commit's release.
The tag is a lightweight reference to the exact checked-out commit. Imported
upstream tags remain unchanged and tag pushes do not trigger this workflow.

Allocation and publication are serialized across workflow runs. A queued run
whose source commit has been superseded by code changes on `fork-release`
skips publication. A later push containing only ignored documentation changes
does not cancel an earlier code release: the resolver fetches the current head,
checks ancestry, and compares the trees excluding the same documentation paths.
The active run is allowed to finish. With GitHub's default single pending slot,
newer pushes can replace an older waiting run; this branch tracks the latest
pushed state rather than promising a separate release for every intermediate
push. See [workflow concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
The same commit reuses an existing reserved tag, including a tag whose build
failed or whose release is still a draft. If the commit has already been
published under its generated tag, the build and release jobs are skipped.
Existing numbered tags and published assets are not renamed or rewritten.

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
2. `prepare`: download `codex-package-<upstream-target>.tar.gz` and its official checksum
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

Linux GNU/glibc, macOS, and Windows packages are built for x86_64 and ARM64 using
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

## Linux glibc 2.38 compatibility

The fork's Linux packages target `x86_64-unknown-linux-gnu` and
`aarch64-unknown-linux-gnu`, with glibc 2.38 as the supported runtime floor.
They build natively on `ubuntu-22.04` and `ubuntu-22.04-arm`.
[GitHub lists both runner labels](https://docs.github.com/en/actions/reference/runners/github-hosted-runners);
[Ubuntu 22.04 supplies glibc 2.35](https://packages.ubuntu.com/jammy/libc6),
which keeps CLI imports below the 2.38 compatibility ceiling. The workflow
installs ordinary GNU build dependencies and no longer invokes Zig or the
musl/OpenSSL toolchain setup. This does not promise support below glibc 2.38.

`fork_release.py` maps each Linux GNU target to the corresponding upstream
musl package **only for resource acquisition and original-package validation**.
The output archive, `codex-package.json.target`, and voice manifest `appTarget`
identify the actual GNU CLI. Package metadata records `minimumGlibc: "2.38"`;
both package metadata and `fork-build.json` record `upstreamTarget` separately.
The original voice runtime target, commit, receipts, and helper bytes remain
unchanged. Other platforms retain their original target mapping.

The Unix installer selects GNU archives for Linux. Its retired-release cleanup
recognizes both GNU and older musl directory names. Legacy npm archives retain
their musl vendor-directory mapping. Daemon staging already selects GNU targets
for a GNU CLI in `app-server-daemon/src/prepare_install.rs`.

After assembly, [`check_linux_glibc.py`](../../.github/scripts/check_linux_glibc.py)
uses `readelf --version-info --wide` on every ELF file, including nested voice
libraries and reused helpers. It rejects imported GLIBC versions newer than
2.38, private/unknown glibc ABI requirements, and a package with no ELF files.
Version definitions are ignored; `GLIBC_ABI_DT_RELR` is treated as requiring
2.36. Failure prevents artifact upload and publication. CLI and voice helper
identity smoke checks also run on the older build runner.

On 2026-11-10, both actual upstream `rust-v0.167.0` Linux archives were downloaded
and verified against the release's `codex-package_SHA256SUMS`. Each contained
32 ELF files; both passed the checker, and the highest required GLIBC version
was 2.28. These results establish the imported-symbol ceiling for the reused
resources at this pinned version. The rebuilt GNU CLI still needs its first
Ubuntu 22.04 Actions build and package check. No complete release run, glibc
2.38 runtime execution, or audio-device/network session was performed here;
symbol checks do not establish kernel, CPU, or other shared-library compatibility.

Local checks for this change passed: 18 release-script tests, 4 glibc-checker
tests (including real versioned ELF providers/consumers), and 20 installer tests.
Actionlint, shell syntax, and whitespace checks also passed. Verification:

```sh
python3 -m unittest discover -s .github/scripts -p test_fork_release.py
python3 -m unittest discover -s .github/scripts -p test_check_linux_glibc.py
python3 scripts/install/test_install_sh.py
actionlint -oneline .github/workflows/rust-release.yml
sh -n scripts/install/install.sh
git diff --check
# After verifying and extracting a release archive:
python3 .github/scripts/check_linux_glibc.py /path/to/package
```

## Windows dependency checkout and build caching

[Run 42757196810](https://github.com/ayanamist/codex/actions/runs/42757196810)
built `f146e4071ae7e6e30d6021f8952113e711877152`, before the Linux GNU change
in `6305206509`. Its Linux results apply to the old musl targets, and do not
validate the current GNU/glibc configuration.
The run completed with `failure` at `2026-11-10T07:38:40Z`: both Windows
targets failed, both Linux musl and both macOS targets succeeded, and publication
was skipped. No other build failure was found in the completed jobs.

Both Windows jobs failed while Cargo was resolving the workspace, before Rust
compilation. The [x86_64 log](https://github.com/ayanamist/codex/actions/runs/42757196810/job/129634479172)
and [ARM64 log](https://github.com/ayanamist/codex/actions/runs/42757196810/job/129634479025)
report `failed to update submodule third_party/rust` followed by `path too long`
and `class=Filesystem (30)`. The dependency was the workspace's pinned
`rusty_v8` patch at `350c5a859a9b3c84ab8701b3ad51e3b7699b30c0`.
Although the CLI does not compile V8, Cargo still checks out that patch and its
submodules during workspace resolution. Omitting the V8 build/download action
does not remove this source checkout requirement.

The failing ICU test snapshot path was 266 characters under
`C:/Users/runneradmin/.cargo`. Placing `CARGO_HOME` at the workspace drive's root
`c` directory (for example `D:/c`) reduces that same path to 243 characters.
The workflow sets this before toolchain/cache operations and enables
`git config --global core.longpaths true`, matching the existing shared CI
setup. Shortening the path addresses Cargo's checkout as well as Git subprocesses;
the Git setting alone was not assumed to fix Cargo's filesystem operations.
Walking the existing local V8 checkout gave a maximum of 252 characters when
mapped to `D:/c/git/checkouts`, also below the traditional limit.
The release workspace, target outputs, and package paths retain their layout.

The observed cold build steps were:

| Target in the observed run | Build step duration | Result |
| --- | --- | --- |
| `x86_64-unknown-linux-musl` | 56 min 54 s | Success, including package checks and upload |
| `aarch64-unknown-linux-musl` | 48 min 20 s | Success, including package checks and upload |
| `aarch64-apple-darwin` | 104 min 34 s | Success, including package checks and upload |
| `x86_64-apple-darwin` | 174 min 19 s | Success, including package checks and upload |

These step durations include dependency resolution/downloads as well as
compilation/linking. Cargo itself reported 56 min 47 s and 48 min 11 s,
respectively; macOS ARM64 reported 104 min 29 s and macOS Intel reported
173 min 35 s. In the Linux ARM64 log,
resolving/downloading git dependencies took
about 3 min 17 s before crate downloads started. The official package download
and verification took only 9 s. The cache API initially listed only two Zig
tarball caches; there was no Cargo cache. This makes Cargo dependency reuse the
first optimization, rather than caching upstream release packages.
For macOS ARM64, the last `Compiling` line was at `05:36:17Z` and Cargo finished
at `06:25:01Z`, leaving about 49 minutes without another compilation-start line.
The old log cannot split this interval between ongoing crate compilation,
optimization, and final linking; dependency cache hits should not be assumed to
remove it. The new timing reports provide a more useful basis for that decision.

The workflow uses
[`Swatinem/rust-cache` v2.9.3](https://github.com/Swatinem/rust-cache/tree/d1527c8f67ef9af357290475d4af4b0fab8f12e0),
pinned to its full commit. It restores Cargo registry/git data and the compiled
third-party dependencies in `codex-rs/target`. The explicit cache namespace
includes the runner label, target triple, and virtual root `Cargo.toml` hash
(including the release profile and patches); the action also keys on host
OS/architecture, installed Rust compiler identities, Cargo/Rust compiler
environment, manifests, lockfile, and Cargo configuration. The native SQLite
flags are set before restoration and included explicitly. The restore step
precedes fork version stamping, so release identity changes do not create a
separate dependency cache. Lockfile changes can restore a compatible previous
cache, with Cargo checking which dependencies need rebuilding. Bump
`prefix-key` when changing native build inputs not included in those keys.

Workspace crate artifacts and installed Cargo binaries are excluded. Each fork
release stamps all local package versions and embeds fork/voice commit inputs,
so caching local crates would add volume without avoiding their rebuild.
Incremental compilation data is also excluded by the action. Only successful
jobs save caches; failed first builds cannot populate an immutable key with an
incomplete dependency set. Cache-service failures fall back to a cold build.

`cargo build --timings` now produces HTML reports, uploaded as separate
`rust-build-timings-<target>` artifacts for seven days. The release download
pattern is still `codex-*`, so timing reports never become release packages.
Already gzipped release archives use artifact `compression-level: 0` to avoid
redundant ZIP compression. Release optimization settings, including ThinLTO and
the three-job memory bound, are retained. On 2026-11-10 the owner explicitly
chose to retain release optimizations and measure cache benefits first.
Disabling ThinLTO is a possible future compile/link tradeoff, but needs runtime
and binary-size measurements first.

The entire Intel macOS job took 178 min 39 s, leaving only 81 s under the
original 180-minute limit, before adding cache restore/save overhead. Its job
budget is now 240 minutes to accommodate cold-build variance and cache saving.
Other targets retain 180 minutes. This provides headroom; it is not a measured
speed improvement.

Limits: the first run with the new cache is cold. Windows checkout success and
warm-cache wall time require a subsequent Actions run with these changes; local
Linux inspection cannot establish Windows filesystem behavior. A local V8
checkout occupied 3.6 GiB before cache compression, so six platform caches may
compete for repository cache capacity. Check actual cache sizes/eviction and
restore/save time before claiming a speedup or increasing retained artifacts.

Verification on 2026-11-10: actionlint, 18 fork-release tests, 4 glibc-checker
tests, 24 release utility tests, 20 installer tests, documentation links,
offline workspace metadata, and whitespace checks passed. No push, rerun,
or publication was performed for this change.
Reproduce the evidence and local checks with:

```sh
gh api repos/ayanamist/codex/actions/runs/42757196810
gh api repos/ayanamist/codex/actions/runs/42757196810/jobs --paginate
gh api repos/ayanamist/codex/actions/jobs/129634479172/logs
gh api repos/ayanamist/codex/actions/jobs/129634479025/logs
gh api repos/ayanamist/codex/actions/caches
actionlint -oneline .github/workflows/rust-release.yml
python3 -m unittest discover -s .github/scripts -p test_fork_release.py
python3 -m unittest discover -s .github/scripts -p test_check_linux_glibc.py
python3 -m unittest discover -s .github/scripts -p test_releases.py
python3 scripts/install/test_install_sh.py
cd codex-rs
cargo metadata --offline --locked --all-features --no-deps --format-version 1
cd ..
git diff --check
```

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
accept legal SemVer suffixes without enumerating names or imposing a hash
length. Generation still uses `fork.<first eight commit characters>`. Validation
rejects empty/doubled identifiers, path separators, whitespace, and numeric
identifiers with leading zeroes. Build metadata (`+...`) is outside this channel.

Update checks compare numeric upstream bases first; within the same base,
different custom suffixes are different build identities from the authoritative
GitHub `latest` endpoint. Hashes are not sorted lexically. Legacy numbered
versions remain installable and compare numerically with one another; clients
can migrate from them to a hash release without suggesting a return to an old
numbered version. The publisher additionally uses GitHub's compare API and only
promotes a candidate whose commit is ahead of or identical to the current
`latest` commit. Older bases and behind/diverged commits cannot replace `latest`.
CLI/server notices describe differing custom identities without claiming that
one hash is older. GitHub's `draft` and `prerelease` flags determine the channel;
the workflow publishes the fork release with `prerelease=false`.

SemVer imposes one edge case on the requested spelling: an eight-character hash
containing only digits and starting with `0` would be an invalid numeric
identifier (for example `fork.01234567`). Generation fails with an explicit
message in that case; it neither changes the hash nor silently extends it.
Use a different source commit. Already-installed binaries retain their old
update-check code until replaced; `codex update` or the standalone installer
can install the new release even if the old startup check does not recognize it.

Do not use four numeric components, which Cargo/SemVer reject, or rely on build
metadata such as `+ayanamist.N` for update precedence. Legacy npm/R2 utilities
retain their conventional alpha/beta channel handling separately from GitHub
Release metadata.

## Verification of documentation filtering and commit-based versions

On 2026-11-10, local verification passed 23 fork-release tests, 24 release
utility tests, 21 Unix installer tests, 10 build-info tests, one daemon release
layout test, 11 TUI version tests, and one CLI doctor comparison test (91 total).
The Git fixture exercises real documentation-only and mixed diffs, including
root Markdown files and non-Markdown assets under `docs/`. Publication fixtures
cover eight-character generation, collision rejection, retries, custom suffixes,
migration from numbered releases, and ahead/identical/behind/diverged commits.
Remote tag/release writes are mocked in these tests.

Read-only live checks still found `rust-v0.167.0-ayanamist.2` as the fork's
published, non-prerelease `latest`. Comparing that tag to
`5d0840ed69be4451d0a3dba14a26e1a833629b5f` returned `status: identical`,
`ahead_by: 0`, and `behind_by: 0`. These checks do not publish the local changes.
Actionlint, shell syntax, relative documentation links, and whitespace checks
also passed. The existing unused-variable warning in
`tui/src/chatwidget/rate_limits.rs` remains.

```sh
python3 -m unittest discover -s .github/scripts -p test_fork_release.py
python3 -m unittest discover -s .github/scripts -p test_releases.py
python3 scripts/install/test_install_sh.py
actionlint -oneline .github/workflows/rust-release.yml
sh -n scripts/install/install.sh
git diff --check
cd codex-rs
cargo test --offline -p codex-build-info --lib
cargo test --offline -p codex-app-server-daemon --lib semver_suffixes_use_the_release_install_layout
cargo test --offline -p codex-tui --lib update_versions::tests --no-default-features
cargo test --offline -p codex-cli --bin codex doctor::updates::tests::is_newer_compares_plain_semver
```

The existing lockfile records local workspace packages as `0.0.0`, while the
workspace manifest uses `0.167.0`, so `--locked` initially rejected the test
invocation. Offline testing temporarily normalized 171 local package versions;
the original lockfile was restored after verifying that dependencies had not
changed. PowerShell execution, the changed Actions trigger/action pin, and
publication of the new format have not been exercised live. No commit or push
was performed.

## Rust toolchain input warning

Investigated on 2026-11-10 against fork commit
`5d0840ed69be4451d0a3dba14a26e1a833629b5f` and
[run 42777286813](https://github.com/ayanamist/codex/actions/runs/42777286813).
Keywords: Rust, toolchain, dtolnay, unexpected input, action pin.

The inspected run passed `needs.resolve.outputs.rust_toolchain` to
`dtolnay/rust-toolchain@e081816240890017053eacbb1bdf337761dc5582`.
That exact [action manifest](https://github.com/dtolnay/rust-toolchain/blob/e081816240890017053eacbb1bdf337761dc5582/action.yml)
declares only `targets`, `target`, and `components`; its parse step hardcodes
`toolchain: 1.95.0`. Therefore the runner warns about the undeclared `toolchain`
input, and the supplied value does not select the installed Rust version.

The [Linux x86_64 job log](https://github.com/ayanamist/codex/actions/runs/42777286813/job/129698986796)
shows the exact warning, the supplied `toolchain: 1.95.0`, installation and
default selection of `1.95.0`, and `rustc 1.95.0` output. The run API reports
success for all six build jobs and publication. The versions matched in this
run; a future change to the resolver output would not change this action's
hardcoded version.

For dynamic selection, use a SHA from the action's `master` history that declares
and reads `inputs.toolchain`, as described in the
[action documentation](https://github.com/dtolnay/rust-toolchain#inputs).
At inspection, `master` resolved to
`683b588c487a69d01f6c6ddf40f036ff682cc2c8`; its manifest was verified to declare
the input and read it into the parse step. The local workflow now uses that SHA
and retains `with.toolchain`; an Actions run is still needed to verify the
changed pin. Removing the input alone would have retained the fixed Rust version.

Read-only verification commands:

```sh
gh api repos/ayanamist/codex/actions/runs/42777286813 --jq '{head_sha, conclusion}'
gh api repos/ayanamist/codex/actions/runs/42777286813/jobs --paginate --jq '.jobs[] | {name, conclusion}'
gh run view 42777286813 --repo ayanamist/codex --job 129698986796 --log | rg 'Unexpected input|toolchain:|rustup toolchain install|rustc 1.95.0'
gh api 'repos/dtolnay/rust-toolchain/contents/action.yml?ref=e081816240890017053eacbb1bdf337761dc5582' --jq .content | base64 -d
gh api 'repos/dtolnay/rust-toolchain/contents/action.yml?ref=683b588c487a69d01f6c6ddf40f036ff682cc2c8' --jq .content | base64 -d
```

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
cargo test --offline -p codex-app-server-daemon --lib semver_suffixes_use_the_release_install_layout
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
