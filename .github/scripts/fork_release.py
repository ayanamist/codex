"""Build fork packages by replacing the upstream CLI and standalone executor."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
import tomllib

from releases import is_valid_release_version

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = "openai/codex"
DOCUMENTATION_GLOBS = ("docs/**", "**/*.md", "**/*.mdx", "**/*.rst", "**/*.adoc", "**/*.mmd")
TARGETS = (
    "x86_64-unknown-linux-gnu",
    "aarch64-apple-darwin",
    "x86_64-pc-windows-msvc",
)


def upstream_target(target: str) -> str:
    # Upstream publishes Linux helper bundles only under the musl triples.
    return target.removesuffix("-gnu") + "-musl" if target.endswith("-linux-gnu") else target


def run(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def github_json(endpoint: str, *, missing_ok: bool = False, data: dict | None = None) -> dict | list | None:
    command = ["gh", "api", endpoint]
    if data is not None:
        command += ["--method", "POST", "--input", "-"]
    result = subprocess.run(
        command, input=json.dumps(data) if data is not None else None,
        text=True, capture_output=True, check=False,
    )
    if missing_ok and result.returncode and "(HTTP 404)" in result.stderr:
        return None
    if result.returncode:
        raise RuntimeError(f"GitHub API request failed: {endpoint}: {result.stderr.strip()}")
    return json.loads(result.stdout)


def parse_tag(tag: str) -> tuple[str, str]:
    version = tag.removeprefix("rust-v")
    if not tag.startswith("rust-v") or not is_valid_release_version(version) or "-" not in version:
        raise ValueError("Expected rust-v<upstream version>-<valid SemVer suffix>")
    return version.partition("-")[0], version


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def emit(path: Path, values: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as output:
        for name, value in values.items():
            if "\n" in value or "\r" in value:
                raise ValueError(f"Multiline output is not supported: {name}")
            output.write(f"{name}={value}\n")


def tag_commit(repository: str, reference: dict) -> str:
    obj = reference["object"]
    for _ in range(8):
        if obj["type"] == "commit":
            return obj["sha"]
        if obj["type"] != "tag":
            break
        obj = github_json(f"repos/{repository}/git/tags/{obj['sha']}")["object"]
    raise ValueError("Fork release tag does not resolve to a commit")


def commit_tag(base: str, commit: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("A full lowercase fork commit is required")
    tag = f"rust-v{base}-fork.{commit[:8]}"
    if commit[:8].isdigit() and commit.startswith("0"):
        raise ValueError("The first eight commit characters form a numeric SemVer identifier with leading zeroes; use another source commit")
    parse_tag(tag)
    return tag


def verify_tag_commit(tag: str, commit: str) -> None:
    _, version = parse_tag(tag)
    identity = version.partition("-")[2]
    suffix = identity.removeprefix("fork.") if identity.startswith("fork.") else ""
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("A full lowercase fork commit is required")
    if suffix and re.fullmatch(r"[0-9a-f]+", suffix) and not commit.startswith(suffix):
        raise ValueError("Fork tag hash does not match the source commit")


def only_documentation_changed(commit: str, head: str, *, ignored_paths: tuple[str, ...] = (), cwd: Path = ROOT) -> bool:
    try:
        run("git", "merge-base", "--is-ancestor", commit, head, cwd=cwd)
    except subprocess.CalledProcessError:
        return False
    changed = run("git", "diff", "--name-only", commit, head, "--", ".",
                  *(f":(exclude,glob){pattern}" for pattern in (*DOCUMENTATION_GLOBS, *ignored_paths)), cwd=cwd)
    return not changed


def automatic_tag(base: str, commit: str, ignored_paths: tuple[str, ...] = ()) -> tuple[str, bool]:
    """Reserve a deterministic commit tag under the workflow's publication lock."""
    repository = os.environ["GITHUB_REPOSITORY"]
    head = github_json(f"repos/{repository}/git/ref/heads/fork-release")
    head_commit = head["object"]["sha"]
    if head_commit != commit:
        run("git", "fetch", "--no-tags", f"https://github.com/{repository}.git", head_commit)
        if not only_documentation_changed(commit, head_commit, ignored_paths=ignored_paths):
            print("This commit has been superseded on fork-release; skipping publication")
            return "", False
    tag = commit_tag(base, commit)
    reference = github_json(f"repos/{repository}/git/ref/tags/{tag}", missing_ok=True)
    if reference is not None:
        if tag_commit(repository, reference) != commit:
            raise ValueError("Fork tag collision: the abbreviated hash points to another commit")
        print(f"Resuming release {tag} for the same commit")
        return tag, True
    try:
        github_json(f"repos/{repository}/git/refs", data={
            "ref": f"refs/tags/{tag}", "sha": commit,
        })
    except RuntimeError:
        # Per-platform workflows resolve concurrently; accept a tag reserved first by a sibling.
        reference = github_json(f"repos/{repository}/git/ref/tags/{tag}", missing_ok=True)
        if reference is None or tag_commit(repository, reference) != commit:
            raise
    print(f"Allocated {tag} for {commit}")
    return tag, True


def resolve(tag: str | None, output: Path, *, ignored_paths: tuple[str, ...] = ()) -> None:
    workspace = tomllib.loads((ROOT / "codex-rs/Cargo.toml").read_text())
    base = workspace["workspace"]["package"]["version"]
    if not is_valid_release_version(base) or "-" in base or base == "0.0.0":
        raise ValueError("Resolve from an upstream release checkout with a stable package version")
    if tag is None:
        commit_tag(base, "a" * 40)
    else:
        tag_base, _ = parse_tag(tag)
        if tag_base != base:
            raise ValueError("Fork tag base must match the unchanged upstream workspace version")
    upstream_tag = f"rust-v{base}"
    release = github_json(f"repos/{UPSTREAM}/releases/tags/{upstream_tag}")
    if release["draft"] or release["prerelease"] or release["tag_name"] != upstream_tag:
        raise ValueError("Helpers must come from a published upstream stable release")
    run("git", "fetch", "--no-tags", f"https://github.com/{UPSTREAM}.git", f"refs/tags/{upstream_tag}")
    upstream_commit = run("git", "rev-parse", "FETCH_HEAD^{commit}")
    run("git", "merge-base", "--is-ancestor", upstream_commit, "HEAD")
    fork_commit = run("git", "rev-parse", "HEAD")
    if tag is not None:
        verify_tag_commit(tag, fork_commit)
    should_publish = True
    if tag is None:
        tag, should_publish = automatic_tag(base, fork_commit, ignored_paths)
    if not tag:
        emit(output, {"should_publish": "false", "should_build": "false"})
        return
    _, version = parse_tag(tag)
    emit(output, {
        "tag": tag, "should_publish": str(should_publish).lower(),
        "should_build": str(should_publish).lower(),
        "version": version, "upstream_tag": upstream_tag,
        "upstream_commit": upstream_commit, "fork_commit": fork_commit,
        "rust_toolchain": tomllib.loads((ROOT / "codex-rs/rust-toolchain.toml").read_text())["toolchain"]["channel"],
    })


def build_cache_settings_hash(manifest: dict) -> str:
    """Keep virtual-root build settings in the restore key, not release identity.

    rust-cache already fingerprints package manifests and locked dependencies,
    and can fall back across dependency changes. The virtual root's profiles
    need explicit coverage, but its package version must not block that fallback.
    """
    workspace = manifest.get("workspace", {})
    package = {key: value for key, value in workspace.get("package", {}).items() if key != "version"}
    settings = {
        "profile": manifest.get("profile", {}),
        "patch": manifest.get("patch", {}),
        "replace": manifest.get("replace", {}),
        "resolver": workspace.get("resolver"),
        "package": package,
    }
    return hashlib.sha256(json.dumps(settings, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def extract_package(archive: Path, destination: Path) -> None:
    destination.mkdir()  # Never extract over an existing package.
    with tarfile.open(archive, "r:gz") as source:
        for member in source.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or "\\" in member.name:
                raise ValueError("Unsafe upstream package path")
            if not (member.isdir() or member.isfile()):
                raise ValueError("Upstream package must contain only regular files and directories")
        source.extractall(destination, filter="data")


def package_file(package: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative:
        raise ValueError("Unsafe package inventory path")
    candidate = package.joinpath(*path.parts)
    if not candidate.is_file() or candidate.is_symlink() or not candidate.resolve().is_relative_to(package.resolve()):
        raise ValueError(f"Missing or unsafe package file: {relative}")
    return candidate


def verify_upstream_package(package: Path, base: str, target: str, commit: str) -> dict:
    metadata = json.loads((package / "codex-package.json").read_text())
    suffix = ".exe" if "windows" in target else ""
    expected = {
        "layoutVersion": 1, "version": base, "target": target,
        "variant": "codex", "entrypoint": f"bin/codex{suffix}",
        "execServer": f"bin/codex-exec-server{suffix}",
        "resourcesDir": "codex-resources", "pathDir": "codex-path",
    }
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError("Upstream package metadata does not match the pinned release")
    for relative in [expected["entrypoint"], expected["execServer"], f"bin/codex-code-mode-host{suffix}", f"codex-path/rg{suffix}"]:
        package_file(package, relative)
    voice = json.loads(package_file(package, "codex-resources/voice/manifest.json").read_text())
    if voice["buildCommit"] != commit or voice["appVersion"] != base:
        raise ValueError("Voice manifest does not match the pinned upstream release")
    if expected["entrypoint"] not in voice["sha256"]:
        raise ValueError("Voice inventory does not include the upstream CLI")
    for relative, expected_digest in voice["sha256"].items():
        if digest(package_file(package, relative)) != expected_digest:
            raise ValueError(f"Upstream voice inventory checksum mismatch: {relative}")
    receipt = json.loads(package_file(package, "codex-resources/voice/runtime.json").read_text())
    if receipt["sourceCommit"] != commit:
        raise ValueError("Voice runtime receipt does not match the pinned upstream commit")
    package_file(package, f"codex-resources/voice/bin/codex-voice-host{suffix}")
    if "linux" in target:
        package_file(package, "codex-resources/bwrap")
    if "windows" in target:
        for helper in ["codex-command-runner.exe", "codex-windows-sandbox-setup.exe"]:
            package_file(package, f"codex-resources/{helper}")
    return metadata


def verify_archive(archive: Path, manifest: Path) -> None:
    matches = []
    for line in manifest.read_text().splitlines():
        checksum, name = line.split(maxsplit=1)
        if name.lstrip("*") == archive.name:
            matches.append(checksum)
    if len(matches) != 1 or matches[0] != digest(archive):
        raise ValueError("Upstream package archive checksum mismatch")


def prepare(args: argparse.Namespace) -> None:
    base, version = parse_tag(args.tag)
    fork_commit = run("git", "rev-parse", "HEAD")
    verify_tag_commit(args.tag, fork_commit)
    if not re.fullmatch(r"[0-9a-f]{40}", args.upstream_commit):
        raise ValueError("A full upstream commit is required")
    resource_target = upstream_target(args.target)
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        archive = directory / f"codex-package-{resource_target}.tar.gz"
        run("gh", "release", "download", f"rust-v{base}", "--repo", UPSTREAM,
            "--pattern", archive.name, "--pattern", "codex-package_SHA256SUMS", "--dir", str(directory))
        verify_archive(archive, directory / "codex-package_SHA256SUMS")
        extract_package(archive, args.package_dir)
    verify_upstream_package(args.package_dir, base, resource_target, args.upstream_commit)
    # Record every reused file before replacement, including resource signatures.
    upstream_files = {
        path.relative_to(args.package_dir).as_posix(): digest(path)
        for path in sorted(args.package_dir.rglob("*")) if path.is_file()
    }
    write_json(args.package_dir / "fork-build.json", {
        "version": version, "upstreamTag": f"rust-v{base}",
        "upstreamCommit": args.upstream_commit, "forkCommit": fork_commit,
        "target": args.target, "upstreamTarget": resource_target, "upstreamFiles": upstream_files,
    })
    values = {
        "CODEX_VOICE_HELPER_COMMIT": args.upstream_commit,
        "STABLE_GIT_COMMIT": fork_commit,
        "FORK_VERSION": version,
        "CODEX_RELEASE_VERSION": version,
    }
    if "linux" in args.target:
        values["CODEX_BWRAP_SHA256"] = digest(args.package_dir / "codex-resources/bwrap")
    emit(args.env_file, values)


def assemble(package: Path, binary: Path, exec_server: Path, output: Path) -> Path:
    provenance_path = package / "fork-build.json"
    provenance = json.loads(provenance_path.read_text())
    base, version = parse_tag(f"rust-v{provenance['version']}")
    metadata = verify_upstream_package(package, base, provenance["upstreamTarget"], provenance["upstreamCommit"])
    entrypoint = metadata["entrypoint"]
    executor = metadata["execServer"]
    rebuilt = {entrypoint: binary, executor: exec_server}
    for source in rebuilt.values():
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"Missing or unsafe fork binary: {source}")
    voice_path = package / "codex-resources/voice/manifest.json"
    mutable = {*rebuilt, "codex-package.json", "codex-resources/voice/manifest.json"}
    original_files = provenance["upstreamFiles"]
    for relative, expected in original_files.items():
        if digest(package_file(package, relative)) != expected:
            raise ValueError(f"Upstream input changed before assembly: {relative}")
    for relative, source in rebuilt.items():
        shutil.copyfile(source, package / relative)
        if os.name != "nt":
            (package / relative).chmod(0o755)
    metadata["version"] = version
    metadata["target"] = provenance["target"]
    metadata["upstreamTarget"] = provenance["upstreamTarget"]
    if provenance["target"].endswith("-linux-gnu"):
        metadata["minimumGlibc"] = "2.38"
    metadata["upstreamTag"] = provenance["upstreamTag"]
    metadata["upstreamCommit"] = provenance["upstreamCommit"]
    metadata["buildCommit"] = provenance["forkCommit"]
    write_json(package / "codex-package.json", metadata)
    voice = json.loads(voice_path.read_text())
    # buildCommit continues to identify the unchanged upstream voice helper.
    voice["appBuildCommit"] = provenance["forkCommit"]
    voice["appVersion"] = version
    voice["appTarget"] = provenance["target"]
    for relative in rebuilt:
        if relative == entrypoint or relative in voice["sha256"]:
            voice["sha256"][relative] = digest(package / relative)
    write_json(voice_path, voice)
    for relative, expected in original_files.items():
        if relative not in mutable and digest(package_file(package, relative)) != expected:
            raise ValueError(f"Reused upstream file changed: {relative}")
    provenance["upstreamFiles"] = {name: value for name, value in original_files.items() if name not in mutable}
    provenance["entrypointSha256"] = digest(package / entrypoint)
    provenance["execServerSha256"] = digest(package / executor)
    provenance["rebuiltBinaries"] = {
        relative: {"sha256": digest(package / relative), "buildCommit": provenance["forkCommit"]}
        for relative in rebuilt
    }
    write_json(provenance_path, provenance)
    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / f"codex-package-{provenance['target']}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in sorted(package.iterdir()):
            archive.add(path, arcname=path.name)
    return archive_path


def release_checksums(repository: str, tag: str, local: dict[str, str]) -> dict[str, str]:
    assets = github_json(f"repos/{repository}/releases/tags/{tag}")["assets"]
    sums = {}
    for target in TARGETS:
        name = f"codex-package-{target}.tar.gz"
        asset = next((item for item in assets if item["name"] == name), None)
        if asset is None:
            continue
        value = local.get(name) or (asset.get("digest") or "").removeprefix("sha256:")
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError(f"No SHA-256 digest is available for {name}")
        sums[name] = value
    return sums


def publish(tag: str, directory: Path) -> None:
    """Add this platform's package to the release, creating the release on first use."""
    _, version = parse_tag(tag)
    archives = [path for target in TARGETS if (path := directory / f"codex-package-{target}.tar.gz").is_file()]
    if not archives:
        raise ValueError("No platform package to publish")
    commit = run("git", "rev-parse", "HEAD")
    verify_tag_commit(tag, commit)
    repository = os.environ["GITHUB_REPOSITORY"]
    for source in ["install.sh", "install.ps1"]:
        shutil.copyfile(ROOT / "scripts/install" / source, directory / source)
    existing = github_json(f"repos/{repository}/releases/tags/{tag}", missing_ok=True)
    if existing is None or existing["draft"]:
        notes = directory / "release-notes.md"
        write_release_notes(notes, tag, version, commit, repository)
        if existing is None:
            try:
                run("gh", "release", "create", tag, "--repo", repository, "--verify-tag", "--prerelease", "--latest=false", "--title", version, "--notes-file", str(notes))
            except subprocess.CalledProcessError:
                # A sibling platform workflow may have created the release first.
                if github_json(f"repos/{repository}/releases/tags/{tag}", missing_ok=True) is None:
                    raise
        else:
            run("gh", "release", "edit", tag, "--repo", repository, "--draft=false", "--prerelease=true", "--latest=false")
    fixed = [directory / name for name in ["install.sh", "install.ps1"]]
    run("gh", "release", "upload", tag, "--repo", repository, "--clobber", *(str(path) for path in archives + fixed))
    # Sibling uploads may race with this one; rewrite the checksums until the archive set is stable.
    local = {path.name: digest(path) for path in archives}
    published = None
    for _ in range(5):
        sums = release_checksums(repository, tag, local)
        if sums.keys() == published:
            break
        checksums = directory / "codex-package_SHA256SUMS"
        checksums.write_text("".join(f"{value}  {name}\n" for name, value in sums.items()), encoding="utf-8")
        run("gh", "release", "upload", tag, "--repo", repository, "--clobber", str(checksums))
        published = sums.keys()
    else:
        raise RuntimeError("Release assets kept changing while writing checksums")
    # Releases stay prereleases; promote one manually with `gh release edit --prerelease=false --latest`.


def write_release_notes(notes: Path, tag: str, version: str, commit: str, repository: str) -> None:
    base, _ = parse_tag(tag)
    notes.write_text(
        f"Fork CLI {version}, based on [{UPSTREAM} rust-v{base}]"
        f"(https://github.com/{UPSTREAM}/releases/tag/rust-v{base}).\n\n"
        f"Fork commit: [`{commit}`](https://github.com/{repository}/commit/{commit}). "
        "`codex` and `codex-exec-server` are rebuilt; other helpers and native voice "
        "resources are reused from the pinned upstream release.\n\n"
        "Packages are provided for Linux x64, macOS ARM64, and Windows x64.\n\n"
        "Linux packages require glibc 2.38 or newer; their CLI targets GNU Linux, "
        "with upstream helpers reused from the corresponding musl package.\n\n"
        "The fork executable does not carry OpenAI's signing identity. "
        "macOS builds use an ad hoc signature.\n", encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    resolve_parser = commands.add_parser("resolve")
    resolve_parser.add_argument("--tag", help="Explicit tag; otherwise allocate or resume a release for this commit.")
    resolve_parser.add_argument("--github-output", required=True, type=Path)
    resolve_parser.add_argument("--ignored-path", action="append", default=[], help="Path whose changes never supersede a queued release; repeatable.")
    cache_parser = commands.add_parser("cache-key", help="Fingerprint virtual-root build settings before release stamping.")
    cache_parser.add_argument("--github-output", required=True, type=Path)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--tag", required=True)
    prepare_parser.add_argument("--upstream-commit", required=True)
    prepare_parser.add_argument("--target", choices=TARGETS, required=True)
    prepare_parser.add_argument("--package-dir", required=True, type=Path)
    prepare_parser.add_argument("--env-file", required=True, type=Path)
    assemble_parser = commands.add_parser("assemble")
    assemble_parser.add_argument("--package-dir", required=True, type=Path)
    assemble_parser.add_argument("--binary", required=True, type=Path)
    assemble_parser.add_argument("--exec-server-binary", required=True, type=Path)
    assemble_parser.add_argument("--output-dir", required=True, type=Path)
    publish_parser = commands.add_parser("publish")
    publish_parser.add_argument("--tag", required=True)
    publish_parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "resolve":
        resolve(args.tag, args.github_output, ignored_paths=tuple(args.ignored_path))
    elif args.command == "cache-key":
        manifest = tomllib.loads((ROOT / "codex-rs/Cargo.toml").read_text())
        emit(args.github_output, {"build_settings_hash": build_cache_settings_hash(manifest)})
    elif args.command == "prepare":
        prepare(args)
    elif args.command == "assemble":
        print(assemble(args.package_dir, args.binary, args.exec_server_binary, args.output_dir))
    else:
        publish(args.tag, args.directory)


if __name__ == "__main__":
    main()
