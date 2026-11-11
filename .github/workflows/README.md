# Fork build and release workflow

Scope: `ayanamist/codex`, reviewed on 2026-11-10 against workspace version
`0.167.0` and the accompanying fork changes.
Keywords: GitHub Actions, fork, upstream package, release, voice, version, glibc,
GNU, Windows, MAX_PATH, Cargo, cache, timings, commit hash, SemVer suffix,
paths-ignore.

Only [`rust-release.yml`](rust-release.yml) remains. Pushing to `fork-release`
automatically selects a tag such as `rust-v0.167.0-fork.5d0840ed`, builds the
fork's `codex` entrypoint for Linux GNU/glibc x64, macOS ARM64, and Windows x64,
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

`codex-cli --bin codex` and `codex-exec-server-cli --bin codex-exec-server` are
built together, then both replace their upstream counterparts in the package.
The packaged binaries must both report the fork version. Code-mode host, voice
helper/runtime, ripgrep, and platform sandbox helpers are reused from the pinned
upstream package, with unchanged file contents verified. V8, lint tools, and
separate app-server binaries are not built here. `fork-build.json` records the
fork commit and digest for each rebuilt binary.

Windows jobs use a short Cargo home at the workspace drive root and enable Git
long paths before dependency resolution. Both Windows jobs in run `42757196810`
previously failed on a V8/ICU submodule snapshot path. Before any Cargo metadata
or build command, the workflow now downloads a checksum-pinned 405 KB snapshot
of the same rusty_v8 commit and configures Cargo source replacement. The 163
tracked files preserve the Rust patches without fetching V8/ICU submodules;
Cargo.toml and the locked git identity are preserved. This CI path forces the
prebuilt native-library mode. See the [source preparation and Linux runtime
verification](../../docs/fork/release-management.md#avoiding-v8-submodule-downloads).

Each target caches Cargo registry/git data and compiled third-party crates with
`Swatinem/rust-cache`, pinned to v2.9.3's commit. Cache identity includes the
runner/target, Rust/compiler environment, manifests, and lockfile. Internal
package identities remain `0.0.0`; executable entry points embed the release
version and commit. The `fork-release-v2` cache retains other git dependencies for reuse;
the large V8/ICU git tree is never fetched because V8 uses the small snapshot
described above. Workspace crates and installed Cargo tools remain excluded.
Successful jobs save the cache. Cargo HTML timings are retained as
separate `rust-build-timings-*` artifacts for seven days, outside the release's
`codex-*` download pattern. Gzipped packages upload without redundant ZIP
compression. See the [diagnosis, baseline, and cache limits](../../docs/fork/release-management.md#windows-dependency-checkout-and-build-caching).
Updated on 2026-11-11: the explicit cache-key fingerprint covers root build
settings rather than the entire root manifest, allowing reuse across version
changes. Rust builds also use the official sccache action pinned to v0.0.11's
commit and sccache v0.19.0 with the GHA backend. Initial hit/miss/non-cacheable
JSON statistics accompany the timing artifact. On manual dispatch,
`verify_compiler_cache=true` builds without allocating a tag or publishing a
release, then cleans Cargo release artifacts and builds again to measure
sccache reuse. The warm metrics use a separate `rust-warm-build-timings-*`
artifact; normal releases still build once. See the
[implementation, upstream version distinction, and remote probe](../../docs/fork/release-management.md#build-time-version-adaptation-without-upstream-source-churn).
All three targets have a 180-minute timeout. Release optimization settings are
retained. Run `42777286813` uploaded caches for all six former targets; the cache
API subsequently retained only the two macOS entries, consistent with capacity
eviction. The three retained targets' old caches totaled about 11.7 GB. A local
same-revision V8 checkout alone compressed to about 2.94 GB, motivating the
source replacement; new Actions cache sizes and warm-build times remain unmeasured. See
the [observed cache sizes and timing evidence](../../docs/fork/release-management.md#cache-retention-and-three-platform-release-scope).

Linux CLI builds use Ubuntu 22.04 runners (glibc 2.35) to support glibc 2.38
and newer. GNU output metadata records the upstream musl resource target
separately. Before upload, every packaged ELF file is checked for GLIBC imports
above 2.38, including the reused voice runtime and helpers. The Unix installer
selects the GNU archives. See the [compatibility contract](../../docs/fork/release-management.md#linux-glibc-238-compatibility)
for evidence and runtime verification limits.

The integration branch retains its original Cargo.toml/Cargo.lock for this change. `resolve`
selects the upstream release from that original manifest. In the disposable
build checkout, `prepare_fork_sources.py` normalizes internal package identities
to `0.0.0` and adapts version consumers before metadata/cache restoration.
`prepare` exports `CODEX_RELEASE_VERSION`; executable entry points initialize
`codex-build-info` and adapted libraries read its runtime version interface.
The script scans new source files automatically and rejects unsupported version
syntax before writing; it does not depend on a saved upstream patch. Its report
is included in the build timings artifact. There is no bulk consumer diff or
separate upstream version pin in the integration branch.
Installers, startup/doctor update checks, and daemon
installation accept arbitrary legal SemVer suffixes, with no hash-length check.
Generated versions use `fork.<eight characters>`; historical numbered releases
remain supported. GitHub Release flags determine the stable channel. See
[release management](../../docs/fork/release-management.md) for the release
procedure, metadata contract, source evidence, and verification commands.

The release publishes three `codex-package-<target>.tar.gz` files,
`codex-package_SHA256SUMS`, the fork's `install.sh` and `install.ps1`, and
`config-schema.json`. A first release can become `latest`; an older upstream
base cannot replace a newer `latest`, and GitHub commit comparison prevents a
behind or diverged source commit from replacing it. Hashes are never ordered
lexically. Published releases cannot be
overwritten; failed drafts can be retried.

The new macOS CLI and executor use ad hoc signatures; their Windows equivalents
are not Authenticode signed. Reused upstream binary signatures are preserved. No
OpenAI signing credentials, BuildBuddy, custom runners, npm, PyPI, R2, WinGet,
DMG publication, or website deployment are required. PR/post-merge CI, test
suites, lint, and Issue/PR automation remain removed. The workflow's version and
resource checks are release integrity checks.

Local validation:

```sh
actionlint -oneline .github/workflows/rust-release.yml
python3 -m unittest discover -s .github/scripts -p test_fork_release.py
python3 -m unittest discover -s .github/scripts -p test_prepare_rusty_v8_source.py
python3 -m unittest discover -s .github/scripts -p test_check_linux_glibc.py
python3 -m unittest discover -s .github/scripts -p test_releases.py
python3 scripts/install/test_install_sh.py
git diff --check
```

No workflow run or publication was triggered locally. The reduced matrix and
warm-cache performance still require an Actions run; platform installation
remains separate verification. Branch protection may
still reference removed checks and requires a repository settings change if so.
