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
Release targets were reduced on 2026-11-10 against `17a0203a0b`, workspace
version `0.167.0`, and the logs/cache evidence from Actions run `42777286813`.
V8 source retrieval and cache reduction were implemented on the same date
using the exact commit's root snapshot, Cargo source replacement, and an
independently pinned archive checksum. Registry, remaining git sources, and
third-party build artifacts retain the standard rust-cache policy.
Standalone-executor build and packaging coverage was fixed on the same date
against the current fork changes; CLI and executor now share the fork build.
Updated on 2026-11-11 against `47864b7bb4` plus local changes: internal Cargo
versions are normalized to `0.0.0` only in a disposable build checkout; the
integration branch retains upstream sources, and final executables stamp
release identity through `codex-build-info`.
Keywords: fork, release, upstream tag, version, helpers, V8, voice, installer,
glibc, GNU, Windows, MAX_PATH, Cargo, cache, build timings, commit hash,
SemVer suffix, paths-ignore, platform matrix, x64, ARM64, cache eviction,
source replacement, V8 snapshot, submodules.

## Compiler-cache investigation: run 42941045713

Investigated on 2026-11-11 against successful release run
[`42941045713`](https://github.com/ayanamist/codex/actions/runs/42941045713),
source `74593b74690c7bba7e9a68ddd0fdb5c6e3ac61b2`, upstream `0.167.1`,
and local checkout `47864b7bb4`. This initial diagnosis preceded the
compiler-cache implementation documented in the next section. Evidence comes
from the run/jobs APIs, downloaded job logs, all three Cargo timing artifacts,
the cache API snapshot, and the pinned rust-cache implementation. No build,
test, dependency installation, or sccache benchmark was performed at that stage.

### Observed build work

The workflow took 94 min 25 s from creation to its final update. The following
durations exclude setup, packaging, and cache upload:

| Target | Build step | Final `codex` bin task | `codex-tui` library | `codex-core` library |
| --- | --- | --- | --- | --- |
| Linux x64 GNU | 53 min 26 s | 25 min 56 s | 9 min 6 s | 7 min 10 s |
| Windows x64 MSVC | 63 min | 30 min 8 s | 10 min 48 s | 8 min 13 s |
| macOS ARM64 | 90 min 33 s | 36 min 9 s | 28 min 51 s | 15 min 1 s |

Build-step durations come from the jobs API; task durations come from the
uploaded `rust-build-timings-*` HTML files. Tasks overlap, so columns must not
be summed. The final bin task includes compiler/codegen/optimization/link work;
these artifacts do not isolate system-linker time. Both the run and local
workspace use `lto = "thin"`, `codegen-units = 4`, three Cargo jobs, and the
workflow's `CARGO_PROFILE_RELEASE_DEBUG=0` override. ThinLTO can increase final
link-time optimization work; its share of the bin duration was not separately
profiled. See [Cargo profile semantics](https://doc.rust-lang.org/cargo/reference/profiles.html#lto).

Summing task durations, rather than elapsed time, gives about 1,294/1,439/1,440
seconds of third-party work for Linux/Windows/macOS, versus
5,388/6,417/10,188 seconds for packages carrying this fork's stamped version.
The last third-party task finishes about 13 min 43 s / 16 min 11 s /
16 min 30 s after the build starts. These measurements show that substantial
workspace and executable work remains after third-party compilation. They are
not predictions of warm-cache savings because scheduling and overlap change.

### Confirmed unnecessary cold cache

All three restore logs say `No cache found.` The previous successful run
[`42820664456`](https://github.com/ayanamist/codex/actions/runs/42820664456)
had saved caches using the same `fork-release-v2` prefix. Its root manifest
differs from this run only in `[workspace.package].version`, `0.167.0` to
`0.167.1`. However, the workflow embeds the entire root manifest hash in the
user-supplied cache key:

```yaml
key: ${{ matrix.runner }}-${{ matrix.target }}-${{ hashFiles('codex-rs/Cargo.toml') }}
```

The old/new root-manifest hashes differ, while the automatic compiler/env
and dependency-hash suffixes are unchanged on each platform. The pinned
action's fallback restore key retains the complete user-supplied key; it only
drops the final automatic manifest/lock/config hash. Consequently, even a
version-only root-manifest change blocks fallback to the previous cache.
See the pinned [key construction](https://github.com/Swatinem/rust-cache/blob/d1527c8f67ef9af357290475d4af4b0fab8f12e0/src/config.ts)
and [restore implementation](https://github.com/Swatinem/rust-cache/blob/d1527c8f67ef9af357290475d4af4b0fab8f12e0/src/restore.ts).

The cache API snapshot during this investigation retained all six old/new
entries, about 7.09 GiB in total. This run saved approximately 1.26 GiB for
Linux, 1.20 GiB for Windows, and 1.08 GiB for macOS. The evidence identifies
key invalidation, rather than eviction, as the cause of this run's misses.
This does not rule out future storage-pressure eviction.

The existing action already caches **compiled third-party artifacts**, as
well as dependency downloads. The first improvement should be to fingerprint
the virtual workspace's actual build settings separately from its release
version. Retain relevant profile, patch, target/native inputs and existing
compiler/environment isolation, while allowing ordinary manifest/dependency
changes to use the action's fallback. Do not simply remove all explicit
root-manifest coverage: the pinned implementation traverses package-member
manifests, whereas this virtual root owns the release profile.

### What an additional compiler cache can cover

[Mozilla sccache's Rust support](https://github.com/mozilla/sccache/blob/main/docs/Rust.md)
can cache ordinary library rustc invocations, including workspace libraries.
It cannot cache invocations that use a system linker, including `bin`,
`dylib`, `cdylib`, and `proc-macro` crates. Build-script binaries and script
execution likewise are not replaced by a library compiler-cache hit. In
particular, it cannot directly reuse the final `codex` or standalone executor
bin task above. Rust incremental compilation must be disabled; release already
defaults to disabled, and rust-cache also sets `CARGO_INCREMENTAL=0`.

This repository has another obstacle to workspace cache reuse:
[`set_workspace_version`](https://github.com/ayanamist/codex/blob/74593b74690c7bba7e9a68ddd0fdb5c6e3ac61b2/.github/scripts/fork_release.py#L178)
changes all inherited workspace package versions and their lockfile identities
to the new commit-derived fork version before every release build. Inference:
changed package identities/compiler inputs and version-bearing environment
values are likely to invalidate a large portion of workspace compiler-cache
entries, even when library source files did not change. Sccache hit rates across
newly stamped releases have not been measured. Enabling
`cache-workspace-crates: true` alone also does not make Cargo treat changed
package identities as fresh.

Separating release identity from internal library package versions could make
workspace caching more useful, but requires a separate contract review. Many
production paths read `env!("CARGO_PKG_VERSION")`, including the TUI version,
update checks, app server identity, and telemetry. Stamping only two executable
packages without addressing these consumers would change visible behavior.

The [official sccache action](https://github.com/Mozilla-Actions/sccache-action)
and [GHA backend](https://github.com/mozilla/sccache/blob/main/docs/GHA.md)
support `RUSTC_WRAPPER=sccache` with `SCCACHE_GHA_ENABLED=true`. This is a viable
trial after the existing cache-key issue is fixed, with pinned versions and
hit/miss/non-cacheable statistics. Its remote entries share repository cache
storage with rust-cache. `SCCACHE_CACHE_SIZE` limits the local disk backend,
not remote GHA storage; see [sccache configuration](https://github.com/mozilla/sccache/blob/main/docs/Configuration.md).

Recommended order: fix the existing restore-key invalidation; measure a warm
build with unchanged compiler flags; then evaluate sccache against both a
repeat build and a new commit-derived release. If the workspace stamping
prevents useful hits, review release identity separately. If the final bin
task remains dominant, evaluate ThinLTO/codegen changes with binary-size and
runtime measurements; compiler caching alone does not remove that work.

### Evidence retrieval and limitations

```sh
gh api 'repos/ayanamist/codex/actions/runs/42941045713/jobs?per_page=100'
gh api repos/ayanamist/codex/actions/runs/42941045713/logs > /tmp/codex-42941045713-logs.zip
gh api 'repos/ayanamist/codex/actions/runs/42941045713/artifacts?per_page=100'
# Cargo timing artifacts: Linux, Windows, macOS respectively.
gh api repos/ayanamist/codex/actions/artifacts/13823870185/zip > /tmp/codex-42941045713-linux-timings.zip
gh api repos/ayanamist/codex/actions/artifacts/13824280814/zip > /tmp/codex-42941045713-windows-timings.zip
gh api repos/ayanamist/codex/actions/artifacts/13824499818/zip > /tmp/codex-42941045713-macos-timings.zip
gh api 'repos/ayanamist/codex/actions/caches?per_page=100'
git diff aeae161db7 74593b7469 -- codex-rs/Cargo.toml
rg -n 'CARGO_PKG_VERSION' codex-rs/cli/src codex-rs/tui/src codex-rs/exec-server codex-rs/app-server/src
```

The timing HTML embeds a JSON `UNIT_DATA` array with package version, target,
start, duration, and optional frontend/codegen sections. Grouping by the
`0.167.1-fork.74593b74` version yields the workspace/third-party totals above.
Artifacts and logs have retention limits; cache listings are mutable snapshots.
No full-release warm-build speedup or optimization-setting change was validated.
The targeted remote library probe in the next section establishes a narrower
sccache result. No local compilation was performed.

## Compiler-cache implementation and upstream version semantics

Implemented and verified on 2026-11-11 against checkout `47864b7bb4`, workspace
`0.167.1`, plus these uncommitted changes. Scope: release cache identity, pinned
sccache integration, a manual cache benchmark, and version-stamping diagnosis.
Release optimization settings and the existing runtime version contract are
retained. Keywords: sccache, cache-key, benchmark-only, workspace version,
`0.0.0`, package identity, ThinLTO.

### Upstream development versions differ from release-tag versions

Upstream `main` uses `[workspace.package].version = "0.0.0"`. However,
the upstream release commit
[`0a94398fa6`](https://github.com/openai/codex/commit/0a94398fa60c4fac0e7659e4213a0a36e613dd46)
for `rust-v0.167.1` changes exactly that field from `0.0.0` to `0.167.1`.
The preceding commit still has `0.0.0`. The fork inherited `0.167.1` when it
merged this release tag; this particular change was not introduced by the fork.
The unchanged upstream lockfile still records 171 local packages as `0.0.0`.

The fork adds a separate transformation: `prepare` changes all inherited
workspace package versions to `0.167.1-fork.<commit>`. This has an observed
compiler-cache cost, even for source-identical internal libraries. It is not
necessary to change every internal library's Cargo identity just to identify
the delivered application. Nevertheless, simply removing the transformation
would change existing behavior: Clap version output, the TUI version constant,
update checks, telemetry and several protocol fields read `CARGO_PKG_VERSION`.
`BuildInfo` already reads package metadata for some runtime identities, but
that does not cover all of these consumers.

The deeper change, implemented below, makes application release identity an
explicit runtime/build-info input while keeping internal package identities
stable, then migrate the consumers and their tests together. Restoring the
entire integration workspace to `0.0.0` alone does not implement that contract:
the current resolver also derives the pinned upstream release from the workspace
version. The initial cache change measured that cost; the subsequent version
migration below removes the coupling while preserving application identities.

### Implemented cache behavior

`fork_release.py cache-key` now emits a stable SHA-256 of the virtual root's
profile, patch, replacement, resolver and inherited package settings, excluding
the package version. Ordinary workspace dependency updates are left to
rust-cache's automatic dependency fingerprint and fallback. Native compiler
inputs remain covered by the existing rust-cache environment rules and
`LIBSQLITE3_FLAGS`. The workflow no longer uses the entire root manifest hash
as its restore prefix. Switching from the previous key requires a new cache
entry once; no old cache entries were deleted.

The workflow installs `Mozilla-Actions/sccache-action` pinned to commit
`fc920bf0ec8de6ee65d409111f7ec508035751ba` (`v0.0.11`) with sccache
`v0.19.0`. Rust build steps set `RUSTC_WRAPPER=sccache`; the GHA backend uses
the `fork-release-v1` sccache namespace. The existing third-party Cargo cache
remains enabled. Initial builds save JSON hit/miss/non-cacheable statistics
alongside Cargo HTML timings in `rust-build-timings-<target>`.

A manual dispatch with `verify_compiler_cache=true` is a **benchmark only**:
it resolves the pinned upstream package and builds the selected commit without
allocating a tag or publishing a release, including when that commit was
already published. After the first build and metrics upload, it cleans the
release target directory, resets sccache counters, and repeats the same build.
The second metrics artifact is `rust-warm-build-timings-<target>`. Normal pushes
and default manual dispatches keep the single-build release procedure. All
three matrix targets and the existing workflow serialization still apply.
The warm benchmark adds another full executable optimization/linking pass and
is disabled by default.

### Targeted remote measurement

With user approval, the official Linux musl sccache `v0.19.0` prebuilt archive
was installed on the configured remote build host after verifying SHA-256
`aa73c7270c997894038c0d8f0d297865f57569e1687883322bc431713d4bb9dd`.
The probe ran through the personal remote-dev tool using Rust/Cargo 1.95.0,
four Cargo jobs, `--release --target x86_64-unknown-linux-gnu`, release debug
zero, and incremental compilation disabled.

A disposable source copy built the real `codex-build-info` library and its
dependencies. Before every measurement its Cargo target directory was removed,
so Cargo could not simply reuse existing artifacts. The sccache local disk
backend and source paths were preserved across runs:

| Measurement | Elapsed | Rust cache hits | Rust cache misses |
| --- | --- | --- | --- |
| Cold, version `0.167.1-fork.aaaaaaaa` | 14.04 s | 0 | 37 |
| Same version, clean Cargo target | 4.80 s | 37 | 0 |
| Only stamp changed to `0.167.1-fork.bbbbbbbb`, clean target | 4.84 s | 33 | 4 |

The four workspace libraries were `codex-utils-absolute-path`,
`codex-utils-home-dir`, `codex-install-context`, and `codex-build-info`.
All four cacheable internal library tasks missed after the version-only
change; third-party library tasks remained hits. Build-script executables and
proc macros remained non-cacheable. All three Cargo invocations succeeded.
This is a real but small dependency graph, not a full CLI benchmark or a
measurement of the remote GHA backend. It does not establish a release-wide
speedup or macOS/Windows cache behavior.

The local ignored probe is `.cache/remote-dev/probe-release-sccache.py`; its
source copy, timings, logs and JSON results were created below the remote
`.cache/remote-dev/release-sccache-mam310i_/` directory. The personal tool's
README records its invocation. It never edited the owning build mirror's
source files or package versions.

Verification: 28 fork-release Python tests, 24 release-validator tests and
7 V8-source-preparation tests passed on the remote host; the cache-key CLI
smoke check passed there. Local actionlint and Git whitespace checks passed.
The new GitHub Actions flow, complete CLI/executor release builds, remote GHA
cache writes/reads, and cross-platform behavior remain unverified. No commit,
push, workflow dispatch, tag allocation or release publication was performed.

```sh
git show 0a94398fa6 -- codex-rs/Cargo.toml
git show 0a94398fa6^:codex-rs/Cargo.toml
python3 .cache/remote-dev/remote-dev.py exec -- python3 -m unittest discover -s .github/scripts -p test_fork_release.py
python3 .cache/remote-dev/remote-dev.py exec -- python3 -m unittest discover -s .github/scripts -p test_releases.py
python3 .cache/remote-dev/remote-dev.py exec -- python3 -m unittest discover -s .github/scripts -p test_prepare_rusty_v8_source.py
actionlint -oneline .github/workflows/rust-release.yml
git diff --check
```

## Build-time version adaptation without upstream source churn

Implemented on 2026-11-11 against `47864b7bb4` plus local changes. Scope: the
Cargo release workflow, internal package identities and application release
identity. The earlier directly edited consumer migration was withdrawn at the
user's request. Keywords: source preparation, `application_version`,
`CODEX_RELEASE_VERSION`, `0.0.0`, tokenizer, upstream merges, compiler cache.

This change leaves the integration branch's original Cargo.toml and Cargo.lock
unchanged, including its existing fork dependencies.
`resolve` reads the upstream release base from the original workspace version
and verifies the published stable tag and its ancestry as before. There is no
separate version pin to update. The build job then invokes
[prepare_fork_sources.py](../../.github/scripts/prepare_fork_sources.py) in its
disposable checkout, before Cargo metadata and cache restoration.

The script plans all edits before writing any source. It normalizes inherited
internal package versions to `0.0.0` in the build copy, converts application
version reads to `codex_build_info::application_version()`, and adds the required
internal dependency edges to manifests and Cargo.lock. External package
identities/checksums/sources stay unchanged. The script never inserts a release
version string into libraries, so two releases produce identical adapted
library source when their original source is identical.

The permanent Rust change is the small build-info interface and its tests.
`prepare` exports `CODEX_RELEASE_VERSION` and `STABLE_GIT_COMMIT`; the existing
`initialize!()` macro reads these compile-time inputs only where it expands in
executable entry points. Shared libraries read the initialized application
version at runtime. A compiled stamp takes precedence over package metadata;
without a stamp, valid package metadata is the fallback, then `0.0.0` for an
unpackaged source build. Existing `BuildInfo::initialize(commit)` callers remain
supported.

### Automatic coverage and failure behavior

The adapter scans workspace Rust files and discovers their owning packages;
it does not use a list of upstream file names or a saved patch. Supported
new call sites are picked up on subsequent runs. A Rust lexer skips nested
comments, quoted/raw strings and character literals. Conversion covers:

- Full Cargo version reads, optional reads, and major/minor/patch components.
- Version-dependent `concat!` expressions and string constants, including
  their imports, references and implicit format captures.
- Clap's shorthand version attributes and `crate_version!()` calls.
- Release executable entry points discovered from their Cargo manifests,
  ensuring initialization precedes argument parsing.

Unsupported fields, static/constant shapes, import aliases, shadowed version
constants, or remaining Cargo version keys fail with a source path before any
files are written. Unknown macro aliases/runtime reads cannot silently leave a
literal Cargo version key behind. This is a guarded source adapter, not a full
Rust parser; new unsupported syntax requires extending the adapter and tests.
Code embedded in strings/comments is intentionally preserved, and generated
Rust outside the workspace source scan is outside this conversion's scope.

The current workspace plans 161 changed build-copy files across 29 packages.
Those changes are **not** retained in the owning worktree. The script supports
`--check` for a read-only plan and is idempotent after preparation. Its JSON
report is uploaded with the initial timing/cache statistics artifact. The
report lives outside the Cargo cache so restoring a cache cannot overwrite it.

```sh
# Read-only, no Rust compilation or source changes.
python3 .github/scripts/prepare_fork_sources.py --check
# Only in a disposable checkout, before Cargo metadata/build:
python3 .github/scripts/prepare_fork_sources.py --report build-metrics/fork-source-preparation.json
```

### Verification evidence

The build-info seam was measured remotely with a disposable release-mode probe
linking the real build-info library and Clap. Each round removed Cargo artifacts
and retained only sccache's local backend:

| Measurement | Elapsed | Rust hits | Rust misses | Executable version |
| --- | --- | --- | --- | --- |
| Cold | 13.64 s | 0 | 49 | `0.167.1-fork.aaaaaaaa` |
| Same identity, clean target | 4.35 s | 49 | 0 | `0.167.1-fork.aaaaaaaa` |
| New executable identity, clean target | 4.53 s | 49 | 0 | `0.167.1-fork.bbbbbbbb` |

All cacheable internal libraries remain hits after the executable stamp changes;
`--version` changes correctly. Binary/build-script/proc-macro linker tasks remain
non-cacheable. The ignored probe is `.cache/remote-dev/probe-stable-version.py`;
results are in remote `.cache/remote-dev/stable-version-sccache-a6nkw6hr/`.
This establishes the runtime identity seam, not a full Actions speedup or a
measurement of the remote GHA backend.

A local disposable source copy was prepared with the actual adapter, then
synchronized to the configured remote build mirror using remote-dev's `--source`
option. Its CLI/executor `--offline --locked --all-targets` check passed in
3 min 54 s. The owning workspace was not bulk-rewritten. The preceding direct
migration also built both actual debug binaries. The generated-source copy
was then built separately (6 min 31 s), and both actual executables reported
`0.167.1-fork.bbbbbbbb`. Isolated app-server initialization returned that version
in its User-Agent, and executor initialization returned it in
`environmentInfo.executorVersion`. Subsequent adapter guard improvements were
checked to generate byte-identical Rust/manifests/lockfiles to this verified
build snapshot.

Regression tests cover new upstream source files, idempotence, read-only plans,
unchanged external lock entries, comments/raw strings, constants/formatting,
Clap, invalid/unsupported syntax and all-or-nothing failure before writes.
Build-info tests cover compiled versus package identity and update comparisons.
Final verification passed 40 adapter/fork-release Python tests, 24 release
validator tests, and 12 build-info Rust tests (11 unit and one integration).
Build-info formatting and normal Clippy passed. Strict `-D warnings` Clippy
stops on the unchanged `is_newer_release::key` tuple's pre-existing
`type_complexity` warning; its signature was checked against HEAD and was not
changed to expand this task's scope. Actionlint and Git whitespace checks pass.
The original owning source snapshot is restored to the remote mirror at the
end, preserving its compiled caches.
No changes were committed or pushed, and no Actions run/publication was started.
Windows/macOS builds and release-mode full CLI timings remain unverified.

```sh
python3 .cache/remote-dev/remote-dev.py exec -- python3 -m unittest discover -s .github/scripts -p 'test_*fork*.py'
# Personal helper creates the disposable local generated-source copy.
python3 .cache/remote-dev/prepare-build-copy.py
python3 .cache/remote-dev/remote-dev.py --source .cache/remote-dev/prepared-source exec -- cargo check --offline --locked --manifest-path codex-rs/Cargo.toml -p codex-cli -p codex-exec-server-cli --all-targets
actionlint -oneline .github/workflows/rust-release.yml
git diff --check
```

## Windows source-preparation encoding failure: run 42972181582

Investigated and fixed on 2026-11-11 against `4d9b0c0230` and
[Windows job 130363206427](https://github.com/ayanamist/codex/actions/runs/42972181582/job/130363206427).
Scope: text I/O in `prepare_fork_sources.py`. Keywords: Windows, CP1252,
UTF-8, UnicodeDecodeError, CRLF, source preparation.

The Windows job failed in `Adapt application version reads in the build
checkout`, before Rust compilation. Python 3.12.10 used CP1252 for the
adapter's implicit `Path.read_text()` encoding. The traceback reports undefined
byte `0x81` at offset 93704. The repository's
`app-server/src/config_manager_service_tests.rs` reproduces that exact offset
after its LF input is converted to Windows CRLF; its UTF-8/LF offset is 91046.
The earlier Linux checks did not exercise this Windows default encoding.

All adapter reads and writes now explicitly specify `encoding="utf-8"`,
including Rust files, Cargo manifests/lockfile, and the JSON report. The change
does not depend on a global Python UTF-8 mode setting. The regression test
forces omitted encodings to CP1252 and includes an undefined `0x81` UTF-8
sequence, exercising both LF and CRLF inputs. It failed at the same adapter
read before the fix and passes afterward, including the UTF-8 output round trip.

The CI entry point also starts the adapter with `python -X utf8`, so the entire
interpreter uses UTF-8 defaults for text I/O. Python's UTF-8 mode is selected at
interpreter startup; setting `PYTHONUTF8` inside an already running script would
not switch that process. Explicit file encodings remain useful when `prepare`
is imported into a caller that did not enable the mode. A `coding: utf-8`
source header only declares how to decode the Python source file and would
not change the encoding used to open Rust/TOML files. See
[Python UTF-8 mode](https://docs.python.org/3.12/library/os.html#python-utf-8-mode)
and [text encoding](https://docs.python.org/3.12/library/io.html#text-encoding).

Remote verification passed 41 adapter/fork-release tests. A full-workspace
probe prepared two disposable copies with native UTF-8 and forced legacy
defaults; their conversion reports and all 161 generated files across 29
packages were identical byte for byte. Git whitespace checks passed. This is
a Linux-hosted encoding simulation; a native Windows Actions rerun has not
validated the fix yet. The original run checks out its recorded commit, so
rerunning its failed job alone cannot pick up an uncommitted/new-commit fix.

```sh
python3 .cache/remote-dev/remote-dev.py exec -- python3 -m unittest discover -s .github/scripts -p 'test_*fork*.py'
gh api repos/ayanamist/codex/actions/jobs/130363206427/logs
git diff --check
```

## Upstream integration: rust-v0.167.1

Integrated on 2026-11-11 from fork `aeae161db7` using the exact annotated
upstream tag `rust-v0.167.1` (tag object
`595a35e837a1b6752e60a5de85b89adf415b0ccb`, release commit
`0a94398fa60c4fac0e7659e4213a0a36e613dd46`). `git ls-remote --tags upstream`
confirmed both identities before merging. This adds three upstream commits
covering incremental tool declarations and their Amazon Bedrock restriction.

The sole merge conflict was the workspace version: retain the new upstream
base `0.167.1`, as required by `resolve`'s release-base validation. Fork release
workflows and production overrides otherwise merged without conflicts.
`test_resolve_exports_the_automatic_tag_for_the_same_workflow` previously read
the real workspace manifest while mocking a `0.167.0` release; the upgrade
exposed that mismatch. It now supplies an isolated manifest and toolchain
fixture, so subsequent upstream version changes do not invalidate the test.

The two new regular-Responses snapshots initially failed three cases because
their tool-schema hashes differed from the observed definitions. The observed
namespace hashes match the existing, passing Responses Lite snapshots.
Comparison after stripping `hash=<16 hex digits>` confirmed that the entire
snapshot bodies otherwise matched. Only those hashes were synchronized;
production code and scenario assertions retain the upstream implementation.

Verification passed 47 `codex-features` unit tests, 14 incremental-tool and
resume integration cases, 26 fork-release script tests, 24 general release
script tests, Rust formatting for the affected packages, and Git whitespace
checks. Core integration tests require the `test_stdio_server` helper and the
repository test recipe's 8 MiB thread stack; the first attempt without these
failed on the missing helper and a stack overflow.

```sh
git ls-remote --tags upstream refs/tags/rust-v0.167.1 'refs/tags/rust-v0.167.1^{}'
python3 -m unittest discover -s .github/scripts -p test_fork_release.py
python3 -m unittest discover -s .github/scripts -p test_releases.py
git diff --check --cached
cd codex-rs
cargo fmt -p codex-core -p codex-features -- --check
cargo test --offline -p codex-features --lib
cargo build --offline -p codex-rmcp-client --bin test_stdio_server
RUST_MIN_STACK=8388608 cargo test --offline -p codex-core --test all \
  suite::scenarios::incremental_tools -- --nocapture
```

Cargo normalizes 171 source-less workspace package versions in `Cargo.lock`
from `0.0.0` to `0.167.1` during local testing. Parsed lockfile comparison
confirmed no other package changes; retain the original upstream lockfile
after verification, consistent with the existing release-stamping procedure.
Local tests do not establish that the three platform packages build or that
GitHub release publication succeeds.

## Release procedure

Keep `fork-release` as the integration branch. After upstream publishes a stable
release, fetch its tags and merge the exact release tag. Commit local feature
changes normally. Pushing this branch automatically allocates a fork version,
creates its tag, builds the three platform packages, and publishes a stable
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

The workflow resolves the base from the unmodified upstream workspace version,
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
   inventory, and runtime commit; export the full fork version and commit for
   executable entry points without changing Cargo package identities.
3. `assemble`: require and replace both `bin/codex[.exe]` and
   `bin/codex-exec-server[.exe]`, update package and voice metadata, verify reused
   upstream files are unchanged, and create the new gzip archive.
4. `publish`: require all three platform packages, generate checksums, add the
   fork installers and config schema, upload to a draft, and publish it as a
   stable GitHub Release. Published releases cannot be overwritten. A failed
   draft can be retried. The first release handles an absent latest channel;
   API failures other than HTTP 404 remain failures.

The release builds these three packages on standard GitHub-hosted runners:

| Platform | Target | Runner |
| --- | --- | --- |
| Linux x64 | `x86_64-unknown-linux-gnu` | `ubuntu-22.04` |
| macOS ARM64 | `aarch64-apple-darwin` | `macos-15` |
| Windows x64 | `x86_64-pc-windows-msvc` | `windows-2025` |

Linux ARM64, macOS Intel, and Windows ARM64 are omitted from new releases.
Installers retain architecture detection for historical releases; the newest
release has no native asset for those omitted architectures. Cargo builds only:

```sh
cargo build --locked --release --timings \
  -p codex-cli -p codex-exec-server-cli \
  --bin codex --bin codex-exec-server --target "$TARGET"
```

The workflow preserves code-mode host, voice helper/runtime,
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

The fork's Linux package targets `x86_64-unknown-linux-gnu`, with glibc 2.38 as
the supported runtime floor. It builds natively on `ubuntu-22.04`.
[GitHub lists this runner label](https://docs.github.com/en/actions/reference/runners/github-hosted-runners);
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
third-party dependencies in `codex-rs/target`. The current `fork-release-v2`
policy avoids fetching the large V8 git source via source replacement, as
described below. Other git dependencies remain cached. The explicit cache namespace
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

The earlier Intel macOS job took 178 min 39 s, leaving only 81 s under the
original 180-minute limit, before adding cache restore/save overhead. Its job
budget was raised to 240 minutes to accommodate cold-build variance and cache
saving. The subsequent three-platform scope removes that job; all retained
targets use 180 minutes.

At the time of that change, Windows checkout success and warm-cache wall time
still required a subsequent Actions run. Run `42777286813` below confirms the
Windows checkout fix, but does not establish warm-cache performance. A local V8
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

## Cache retention and three-platform release scope

On 2026-11-10, [run 42777286813](https://github.com/ayanamist/codex/actions/runs/42777286813)
built `5d0840ed69be4451d0a3dba14a26e1a833629b5f` successfully on all six former
targets and published the release. The workflow at that commit and each job's
logs confirm that `Swatinem/rust-cache` ran on Windows, Linux, and macOS.
All six restore logs reported `No cache found.`; each post step uploaded its
archive to 100% without reporting a save failure.

| Target in that run | Build step | Compressed cache bytes | Retained in cache API snapshot |
| --- | --- | ---: | --- |
| Linux x64 | 44 min 15 s | 3,934,438,204 | No |
| Linux ARM64 | 44 min 29 s | 3,902,870,007 | No |
| Windows x64 | 95 min 05 s | 3,943,081,790 | No |
| Windows ARM64 | 69 min 52 s | 3,872,613,823 | No |
| macOS ARM64 | 103 min 21 s | 3,795,054,838 | Yes |
| macOS Intel | 104 min 10 s | 3,797,055,094 | Yes |

The run took 113 min 23 s from its start until its final update. The cache API
snapshot contained two entries totaling 7,592,109,932 bytes, both from the last
two jobs to finish saving. The six uploads total about 23.2 GB. This is
consistent with capacity eviction under GitHub's default 10 GB repository cache
limit, which removes entries by oldest last access; the API snapshot is not
an eviction audit. Reading the repository-specific storage limit returned HTTP
402, so a configured custom limit was not verified. See
[GitHub's cache limits and eviction policy](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching#usage-limits-and-eviction-policy).

The macOS ARM64 Cargo timing artifact also shows expensive workspace work:
`codex-tui` took 1,975.00 s, `codex-app-server` 1,620.65 s, `codex-exec`
1,364.77 s, and `codex-core` 1,023.64 s. The final `codex-cli` binary unit took
2,349.77 s after `codex-tui` completed. These units overlap and cannot be added
as wall time; the binary unit does not separate optimization from final linking.
Third-party dependency cache hits cannot remove all of this workspace work.

At the owner's request, the current matrix and publication requirement retain
only Linux x64, Windows x64, and macOS ARM64. Their measured archives still total
11,672,574,832 bytes (about 11.7 GB), so this reduction alone does not guarantee
cache retention. Per-directory compressed sizes were not measured; the logs
show that Cargo registry, git, and target data are all included. Release
optimization settings and cache policy were unchanged by the platform reduction.
The new three-target workflow and its warm-cache duration remain unverified in
Actions. Local publication tests require each retained package and verify that
the checksum manifest contains exactly the three requested target archives.
Validation for the reduction passed: actionlint, 23 fork release tests, 24
release utility tests, an exact workflow/publication target comparison, and
`git diff --check`. No push, workflow dispatch, or publication was
performed for this reduction.

Evidence and verification commands:

```sh
gh api repos/ayanamist/codex/actions/runs/42777286813
gh api repos/ayanamist/codex/actions/runs/42777286813/jobs --paginate
gh api repos/ayanamist/codex/actions/runs/42777286813/logs > /tmp/codex-actions-42777286813.zip
gh api repos/ayanamist/codex/actions/runs/42777286813/artifacts
gh api repos/ayanamist/codex/actions/artifacts/13750029352/zip > /tmp/codex-timing-macos-arm64.zip
gh api repos/ayanamist/codex/actions/caches
gh api repos/ayanamist/codex/actions/cache/usage
actionlint -oneline .github/workflows/rust-release.yml
python3 -m unittest discover -s .github/scripts -p test_fork_release.py
git diff --check
```

### Cache contents after removing the V8 checkout

The workflow keeps the standard rust-cache registry/git paths and compiled
third-party artifacts. The source replacement below prevents the large V8/ICU
checkout from being created. Other git dependencies such as crossterm can still
be restored with their source timestamps, avoiding extra fetches and rebuilds.
The small V8 snapshot is prepared outside `codex-rs/target` and is not added to
the cache. Workspace crates and installed Cargo tools remain excluded.

The cache prefix changes from `fork-release-v1` to `fork-release-v2`, so the new
workflow does not restore the old oversized immutable entries. Existing remote
entries were not manually deleted. Actual new cache sizes and build times
require a subsequent Actions run; fitting within the repository limit is not
yet a measured result. Release optimization settings and the three-target
matrix remain in place.

### Avoiding V8 submodule downloads

Implemented on 2026-11-10 against fork `17a0203a0b`, workspace `0.167.0`,
`v8` crate `152.2.0`, and rusty_v8 commit
`350c5a859a9b3c84ab8701b3ad51e3b7699b30c0`.
[`prepare_rusty_v8_source.py`](../../.github/scripts/prepare_rusty_v8_source.py)
runs before rust-cache and other Cargo commands in the build job. It downloads
the GitHub source archive for the exact commit, which contains tracked root
files but no recursive submodule contents. The archive's SHA256 is pinned in
[`rusty_v8_152_2_0_source.json`](../../third_party/v8/rusty_v8_152_2_0_source.json).
The script checks the pin against both the workspace git patch and Cargo.lock,
validates the archive, and prepares a directory source with SHA256 checksums
for every extracted file and `package: null` for the original git source.

It appends a git-to-directory source replacement to the CI checkout's existing
`codex-rs/.cargo/config.toml`, preserving existing settings. The directory path
is relative to the workspace so the cache key does not include a per-run
temporary path. Manifest and locked source identity remain unchanged by this
preparation; the separate fork version-stamping step still updates workspace
versions as before. Existing vendor directories and conflicting source/env
settings are not overwritten.
Unknown revisions or checksum mismatches fail instead of falling back to a
full git clone. The generated config forces `V8_FROM_SOURCE=0`; this reduced
source is intended for dependency metadata and prebuilt-native V8 consumers,
not C++ source builds.

| Measured item | Size / result |
| --- | --- |
| Same-commit root source archive | 405,020 bytes |
| Extracted source file contents | 2,018,448 bytes across 163 files |
| Earlier local full checkout compressed with submodules/git data | 2,939,123,173 bytes |
| Linux x64 prebuilt native archive used in the smoke test | 30,220,449 bytes |

All 163 snapshot files were compared byte-for-byte with blobs from the pinned
git commit, including the cppgc Rust fixes. An isolated Cargo 1.95 fixture built
a locked git identity from the directory replacement with a fresh CARGO_HOME,
offline, and without creating a git cache; mutating a checksummed source then
failed verification. The seven preparation tests also cover archive/pin drift,
required source files, existing config preservation, and unsafe archive entries.

An actual full-workspace copy was then prepared and version-stamped as in CI.
Cargo 1.95 metadata with `--locked --offline --all-features --filter-platform
x86_64-unknown-linux-gnu` succeeded with 1,311 packages. The V8 package retained
its original git source identity while its manifest resolved to the reduced
directory source. No V8 git database or checkout appeared in the isolated
Cargo home, and the stamped manifest/lock bytes were unchanged by metadata.
This confirms Linux-filtered workspace resolution, not all-target compilation.
An unfiltered offline metadata attempt stopped at a missing Android
`jni-sys 0.3.1` download; that all-target check did not complete. Missing crates
used for the bounded validation were downloaded only to the temporary home and
checked against Cargo.lock. No global Cargo cache was changed.

For a real native-link test, a separate minimal crate used `v8_enable_sandbox`,
the reduced source, a fresh CARGO_HOME, and the upstream Linux x64 GNU static
library/binding. The three-level manifest/library/binding checksum checks
passed. Cargo 1.95 `run --release --locked --target x86_64-unknown-linux-gnu`
compiled the Rust wrapper and linked the prebuilt library, then successfully
evaluated JavaScript `21 * 2` to `42`. The successful build took 32.94 s;
this is a small smoke build, not a Codex release benchmark. Its CARGO_HOME had
no git directory and its lockfile retained the original git URL and commit.
Earlier unoptimized smoke attempts hit the host filesystem's space limit;
only this task's temporary targets were removed before the release-profile
retry. Downloading the native library and missing Cargo crates for this
temporary validation was explicitly approved by the owner.

The source optimization does not determine which fork Rust entrypoints the
release builds. The standalone-executor fix below separately adds that binary
to the build and overlay. Windows/macOS builds and final cache sizes still
require Actions verification; no workflow or release was triggered.
All local checks below passed: seven source-preparation tests, 23 fork-release
tests, 24 release utility tests, actionlint, and whitespace validation.

Local checks:

```sh
python3 -m unittest discover -s .github/scripts -p test_prepare_rusty_v8_source.py
python3 -m unittest discover -s .github/scripts -p test_fork_release.py
python3 -m unittest discover -s .github/scripts -p test_releases.py
actionlint -oneline .github/workflows/rust-release.yml
git diff --check
```

Run the preparation script only in a fresh/isolated checkout, before Cargo:

```sh
python3 .github/scripts/prepare_rusty_v8_source.py
```

It creates `.cache/fork-v8` and appends source settings to the checkout's Cargo
config. For offline experiments, `--archive` accepts the already downloaded
archive, still requiring the committed checksum to match. See
[Cargo source replacement](https://doc.rust-lang.org/cargo/reference/source-replacement.html)
and [config-relative paths](https://doc.rust-lang.org/cargo/reference/config.html#config-relative-paths).

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
- `fork-build.json` records the fork/upstream source identities, CLI/executor
  digests, a `rebuiltBinaries` map containing each fork binary's commit/digest,
  and original checksums of reused upstream files. When the original voice
  inventory includes the executor, its digest is updated with the CLI digest.

[`BuildInfo`](../../codex-rs/build-info/src/lib.rs) continues to report the
actual fork commit. The upstream runtime's `sourceCommit` is never relabeled as
a fork build. Future changes to voice protocol, code-mode/executor protocol,
or sandbox behavior require checking compatibility with the pinned helpers.

## Source coverage of reused helpers

Audited on 2026-11-10 against fork `17a0203a0b` and upstream
`rust-v0.167.0` (`086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a`). The original
CLI-only packaging rule verified that reused helper bytes matched upstream;
it did not establish that upstream helpers included the fork's source changes.

A conservative traversal of local normal/build dependencies, including all
target-specific and optional edges, found these intersections with the fork's
changed crate files:

| Entrypoint | Local crate closure | Changed source coverage |
| --- | ---: | --- |
| `codex` | 148 | Builds the changed CLI, skills, executor, sandbox, and other library code |
| `codex-code-mode-host` | 28 | No changed local crate files found relative to this upstream tag |
| `codex-exec-server` | 124 | Changed skills, DiscoveryV2, Linux sandbox, build-info, and daemon crates |
| `codex-voice-host` | 8 | Shared realtime client and build-info changes; requires call-path review |
| Windows sandbox helpers | 22 | No changed local crate files found |
| `codex-responses-api-proxy` | 4 | No changed local crate files found |

This source traversal is conservative and does not traverse external crate
edges or prove that every changed function executes in every binary. In
particular, the voice change adapts the CLI-side client handshake to reuse the
upstream helper intentionally; a shared-crate intersection alone does not
prove that helper behavior changed.

The audit found a concrete standalone-executor coverage gap. The fork's
[`capability_discoveries.rs`](../../codex-rs/exec-server/src/discoverV2/capability_discoveries.rs)
resolves the skill frontmatter fallback on the executor side. The CLI's
[`discovery_v2.rs`](../../codex-rs/ext/skills/src/provider/executor/discovery_v2.rs)
copies the returned policy without recomputing it. The CLI's `codex exec-server`
subcommand included the fork library, while the packaged standalone
`bin/codex-exec-server` remained the upstream binary. Connections to that helper
therefore did not gain this fork's DiscoveryV2 fallback just by replacing the
CLI. The build/overlay fix below closes that packaging gap.

Recommended release contract, not yet implemented: compare source/build inputs
against the exact upstream commit for every reused helper and its transitive
dependencies. A changed or unclassified input must require rebuilding the
affected helper or stop publication with a diagnostic. Source comparison must
also account for dependency/configuration changes and deleted inputs; checking
only the helper's own directory is insufficient. Record each packaged binary's
source origin/commit and digest, and test representative fork behavior through
the packaged standalone helper. The current workflow now builds the fork
exec-server; the code-mode host has no identified source change requiring one.
If a future host change requires rebuilding it, reuse the verified V8 native
artifacts described below while compiling the modified Rust host/runtime.

Verification: `git diff --name-status rust-v0.167.0 HEAD`, local TOML dependency
traversal, executor/client routing inspection, and `git diff --check`. Cargo's
full locked dependency-graph recheck remains limited as described below. This
audit identified the packaging fix below. A general dependency-change coverage
guard for other reused helpers has not been implemented.

### Standalone executor build and packaging fix

Implemented on 2026-11-10 against `17a0203a0b` plus the accompanying release
changes. The build job selects both `codex-cli --bin codex` and
`codex-exec-server-cli --bin codex-exec-server` in one Cargo invocation, reusing
shared library work. Both Unix binaries are stripped; both macOS binaries are
ad hoc signed. Windows fork binaries remain unsigned. This adds no V8 build:
the standalone executor has no dependency on the code-mode runtime or host.

The assembler requires `--exec-server-binary` and checks both fork input files
before replacing either. It overlays the executor as well as the CLI, updates
any corresponding voice-inventory digests, and records both binary digests and
their fork commit in `fork-build.json`. Other upstream file contents remain
protected by the existing unchanged-file checks. The workflow then runs both
packaged binaries with `--version`; either reporting an upstream version instead
of the fork version prevents publication. Both packaged ELF files also pass
through the existing glibc ceiling check on Linux.

Before the fix, the archive regression probe returned the upstream fixture's
`signed executor` bytes despite a fork executor input being available. The
regression now checks the extracted package for all three retained targets,
including Windows `.exe` paths, and verifies both fork binaries, inventory
hashes, provenance, and unchanged remaining helpers. A missing executor input
fails before any package file is replaced. Runtime skills-policy behavior of a
complete rebuilt package and additional build time remain Actions validation;
no full local Codex/executor build was attempted under the disk-space limit.
Validation passed: 26 fork-release tests, seven V8 source-preparation tests,
24 release utility tests, four glibc-checker tests, actionlint, and whitespace
checks. An isolated Cargo 1.95 fixture also verified selecting both packages
and their named binaries in one locked invocation. The archive tests exercise
the actual assembler, including the required executor CLI argument and both
upstream inventory shapes (with/without an executor entry).

## V8 and version sources

The original upstream `rust-v0.167.0` Cargo release workflow already downloads
prebuilt V8 native libraries/bindings before compiling its Rust binaries; this
is not a new optimization introduced by the fork. Its
[`rust-release.yml`](https://github.com/openai/codex/blob/rust-v0.167.0/.github/workflows/rust-release.yml#L224-L268)
calls `setup-rusty-v8` for Cargo jobs, then builds the selected binaries,
including the code-mode host. Cargo still fetches the patched git crate and
submodules during workspace resolution. Native V8 source compilation is used
by the separate `rusty-v8-release.yml` artifact producer and Bazel source
consumers; these are distinct from the ordinary Cargo release consumer path.
The upstream
[`third_party/v8/README.md`](https://github.com/openai/codex/blob/rust-v0.167.0/third_party/v8/README.md)
documents these different paths. Merely avoiding native V8 source compilation
does not require skipping a Rust code-mode host build.

V8 is linked by [code-mode-runtime](../../codex-rs/code-mode-runtime/Cargo.toml),
used by the separate [code-mode host](../../codex-rs/code-mode-host/Cargo.toml).
The CLI uses the separate code-mode client and resolves that host through
[`InstallContext`](../../codex-rs/install-context/src/lib.rs). A local manifest
traversal, including normal/build dependencies, all targets and optional
features but excluding dev dependencies, found no V8/runtime/host dependency
path from `codex-cli`. External crate graphs were not traversed. Reusing the
upstream host eliminates rebuilding it and its V8 dependency in this workflow.
An earlier check of Cargo's actual normal/build dependency graph for the Linux
CLI also found no V8, code-mode runtime, or code-mode host. On 2026-11-10, the
current graph recheck with `cargo tree --offline --locked` stopped because
Cargo requested a lockfile update; that failed invocation does not establish
the current graph, and Cargo.lock was not changed for this investigation.
A fresh local-manifest traversal reached 148 normal/build dependency crates,
including all target-specific and optional edges but excluding dev dependencies;
it included the code-mode client and excluded the runtime and host. External
crate dependency edges were not traversed by that source-only check.
The actual six-platform logs from
[run 42777286813](https://github.com/ayanamist/codex/actions/runs/42777286813)
contain no `Compiling v8`, `Compiling codex-code-mode-runtime`, or
`Compiling codex-code-mode-host` entries. They do contain V8 git/submodule
updates during workspace dependency resolution. Fetching those sources does
not mean the release job compiled the V8 C++ engine.

There are two existing levels of upstream reuse:

- The current release workflow reuses the entire upstream
  `bin/codex-code-mode-host[.exe]`. `verify_upstream_package` requires it, and
  `assemble` verifies that its bytes are unchanged while replacing the
  CLI, standalone executor, and package metadata. This also reuses the V8 runtime linked into that
  helper, with no local V8 build or link step.
- If a future change requires rebuilding the host/runtime, the existing
  [V8 download action](../../.github/actions/setup-rusty-v8/action.yml) can
  download Codex-built V8 static libraries and matching generated Rust
  bindings, avoiding a local C++ V8 source build. It is not called by the
  current CLI/executor release workflow because those builds do not need it.

The owner clarified the optimization boundary on 2026-11-10: avoid the expensive
native V8 source build and oversized caches while retaining fork Rust changes.
Reusing the entire upstream host is not required to meet that goal. Rust
host/runtime code can be rebuilt and linked against the matching prebuilt V8
library and bindings. The current workflow builds CLI/executor locally and
continues to reuse the unchanged code-mode host.

The workspace manifests identify only two direct users of the `v8` crate:
`code-mode-runtime` and the experimental `v8-poc` crate. The production host
depends on `code-mode-runtime`; the separate `code-mode` client communicates
with the host and does not link the V8 engine into the CLI/executor. Relevant
inputs and outputs are:

| Layer | Files/paths | Reuse boundary |
| --- | --- | --- |
| Native V8 and C++ dependencies | Pinned rusty_v8 git checkout and submodules; `third_party/v8` build/profile declarations | Use the matching upstream `.a.gz`/`.lib.gz` plus binding asset |
| Rust V8 wrapper | `v8` crate Rust sources and generated `src_binding_*.rs` | Compile the Rust wrapper as needed against the prebuilt native library |
| Runtime | `codex-rs/code-mode-runtime/src/`, including initialization, runtime callbacks and UI engine code | Rebuild modified Rust sources |
| Host process | `codex-rs/code-mode-host/src/` | Rebuild and package the fork binary when needed |
| Experimental V8 consumer | `codex-rs/v8-poc/` | Not a release entrypoint in this workflow |

The oversized source cache and the prebuilt native archive are distinct:
the local git checkout compressed to about 2.94 GB, whereas the verified
upstream release lists compressed native libraries of about 25–42 MB for the
three retained targets. These figures do not establish the final Cargo target
cache size. Excluding Cargo git sources still permits caching registry and
third-party build artifacts. A build using the prebuilt path can still print
`Compiling v8` for the Rust wrapper; that line alone does not mean the C++
engine is being built from source.

Verified on 2026-11-10 against workspace `0.167.0`: Cargo.lock resolves the
`v8` crate to `152.2.0`, patched to
[`seanh-oai/rusty_v8` commit `350c5a859a9b3c84ab8701b3ad51e3b7699b30c0`](https://github.com/seanh-oai/rusty_v8/tree/350c5a859a9b3c84ab8701b3ad51e3b7699b30c0).
The action selects
[`openai/codex` release `rusty-v8-v152.2.0`](https://github.com/openai/codex/releases/tag/rusty-v8-v152.2.0),
published on 2026-09-16 and marked prerelease. Its sandbox/pointer-compression
artifacts exist for all three retained targets:

| Target | Static-library asset | Compressed bytes |
| --- | --- | ---: |
| `x86_64-unknown-linux-gnu` | `librusty_v8_ptrcomp_sandbox_release_x86_64-unknown-linux-gnu.a.gz` | 30,220,449 |
| `aarch64-apple-darwin` | `librusty_v8_ptrcomp_sandbox_release_aarch64-apple-darwin.a.gz` | 24,581,993 |
| `x86_64-pc-windows-msvc` | `rusty_v8_ptrcomp_sandbox_release_x86_64-pc-windows-msvc.lib.gz` | 41,630,799 |

Each library has matching `src_binding_ptrcomp_sandbox_release_<target>.rs`
and `rusty_v8_ptrcomp_sandbox_release_<target>.sha256` assets. The downloaded
bytes of all three checksum manifests matched the committed trust roots in
[`rusty_v8_152_2_0_release_manifests.sha256`](../../third_party/v8/rusty_v8_152_2_0_release_manifests.sha256).
The library/binding asset names in those manifests were also confirmed in the
release asset list. The libraries themselves were not downloaded or linked
during this investigation.

The action verifies the manifest trust root, then both library and binding
checksums, and sets `RUSTY_V8_ARCHIVE` and `RUSTY_V8_SRC_BINDING_PATH`.
The pinned crate's
[`build.rs`](https://github.com/seanh-oai/rusty_v8/blob/350c5a859a9b3c84ab8701b3ad51e3b7699b30c0/build.rs)
consumes those overrides in its prebuilt path; setting `V8_FROM_SOURCE=1`
instead selects a C++ source build. The artifact version, target, and ABI
features must match the consumer. The runtime currently requests
`v8_enable_sandbox`, which implies pointer compression, so it needs the
`ptrcomp_sandbox_release` pair rather than the legacy `release` pair.
Rust wrapper and host/runtime crates still compile when rebuilding that host.
Prebuilt V8 artifacts alone do not change Cargo's original git-fetch behavior.
The fork's source-replacement preparation above now bypasses that fetch in CI.

More precisely, downloading the large C++ source tree is a consequence of this
dependency's git layout, not a requirement of linking the prebuilt native
library. `[patch.crates-io]` replaces `v8 = "=152.2.0"` with the pinned
`seanh-oai/rusty_v8` git repository. Its `.gitmodules` declares V8, ICU, and
other large source repositories, and Cargo recursively fetches submodules by
default before running the crate's `build.rs`. The prebuilt/source decision
and `RUSTY_V8_ARCHIVE` override are evaluated later inside that build script;
they do not change the preceding Cargo git-fetch behavior.

[Cargo's submodule documentation](https://doc.rust-lang.org/cargo/reference/specifying-dependencies.html#git-submodules)
documents both recursive fetching and opting out through
`submodule.<name>.update = none` in the dependency's `.gitmodules`. A consumer
fork with unused source submodules disabled, or a minimal vendored/package
distribution preserving the required Rust patches, could avoid that download
without skipping Rust host/runtime builds. The implemented source replacement
above preserves the git identity and the patched Rust files. Replacing the
fork with the crates.io package remains unvalidated.
The dependency's Cargo `exclude` list trims a published package; it does not
limit Cargo's checkout of a git dependency.

Verification commands (the Cargo-tree command's current limitation is above):

```sh
python3 .github/scripts/rusty_v8_bazel.py resolved-v8-crate-version
gh api repos/openai/codex/releases/tags/rusty-v8-v152.2.0 --jq '{tag_name, published_at, prerelease, assets: [.assets[].name]}'
rg -n 'v8_enable_sandbox|v8_enable_pointer_compression' codex-rs/code-mode-runtime/Cargo.toml
rg -n 'setup-rusty-v8|cargo build' .github/workflows/rust-release.yml
cd codex-rs
cargo tree --offline --locked -p codex-cli --edges normal,build --prefix none --format '{p}'
```

Internal Cargo package versions remain `0.0.0`. Creating a tag alone does not
change `codex --version`: `prepare` exports `CODEX_RELEASE_VERSION`, and the
`codex_build_info::initialize!()` macro embeds it only in executable entry
points. Libraries read `application_version()` at runtime. The upstream base is resolved before source adaptation from the unchanged
integration manifest. Only the disposable build copy normalizes Cargo package
identities and adds the adapter dependencies; `prepare` exports identity inputs.

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

The new macOS CLI and executor are stripped and ad hoc signed, without Apple's
developer signing identity or notarization. Their Windows equivalents are not
Authenticode signed. Reused upstream binaries retain their original signed
bytes. No OpenAI signing credentials, custom runner groups, or BuildBuddy are
required. Platform signing/installation and a complete updated three-platform
Actions build remain unverified. No tag creation, push, workflow run, or release
publication was performed during local verification.
