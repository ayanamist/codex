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

from releases import is_valid_release_version, should_make_latest

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


def only_documentation_changed(commit: str, head: str, *, cwd: Path = ROOT) -> bool:
    try:
        run("git", "merge-base", "--is-ancestor", commit, head, cwd=cwd)
    except subprocess.CalledProcessError:
        return False
    changed = run("git", "diff", "--name-only", commit, head, "--", ".",
                  *(f":(exclude,glob){pattern}" for pattern in DOCUMENTATION_GLOBS), cwd=cwd)
    return not changed


def automatic_tag(base: str, commit: str) -> tuple[str, bool]:
    """Reserve a deterministic commit tag under the workflow's publication lock."""
    repository = os.environ["GITHUB_REPOSITORY"]
    head = github_json(f"repos/{repository}/git/ref/heads/fork-release")
    head_commit = head["object"]["sha"]
    if head_commit != commit:
        run("git", "fetch", "--no-tags", f"https://github.com/{repository}.git", head_commit)
        if not only_documentation_changed(commit, head_commit):
            print("This commit has been superseded on fork-release; skipping publication")
            return "", False
    tag = commit_tag(base, commit)
    reference = github_json(f"repos/{repository}/git/ref/tags/{tag}", missing_ok=True)
    if reference is not None:
        if tag_commit(repository, reference) != commit:
            raise ValueError("Fork tag collision: the abbreviated hash points to another commit")
        existing = github_json(f"repos/{repository}/releases/tags/{tag}", missing_ok=True)
        if existing is not None and not existing["draft"]:
            print(f"Commit already published as {tag}; skipping publication")
            return tag, False
        print(f"Resuming release {tag} for the same commit")
        return tag, True
    github_json(f"repos/{repository}/git/refs", data={
        "ref": f"refs/tags/{tag}", "sha": commit,
    })
    print(f"Allocated {tag} for {commit}")
    return tag, True


def resolve(tag: str | None, output: Path) -> None:
    workspace = tomllib.loads((ROOT / "codex-rs/Cargo.toml").read_text())
    base = workspace["workspace"]["package"]["version"]
    if tag is None:
        commit_tag(base, "a" * 40)
    else:
        base, _ = parse_tag(tag)
    if workspace["workspace"]["package"]["version"] != base:
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
        tag, should_publish = automatic_tag(base, fork_commit)
    if not tag:
        emit(output, {"should_publish": "false"})
        return
    _, version = parse_tag(tag)
    emit(output, {
        "tag": tag, "should_publish": str(should_publish).lower(),
        "version": version, "upstream_tag": upstream_tag,
        "upstream_commit": upstream_commit, "fork_commit": fork_commit,
        "rust_toolchain": tomllib.loads((ROOT / "codex-rs/rust-toolchain.toml").read_text())["toolchain"]["channel"],
    })


def set_workspace_version(root: Path, base: str, version: str) -> None:
    """Change only local workspace package identities in the isolated CI checkout."""
    manifest = root / "codex-rs/Cargo.toml"
    workspace = tomllib.loads(manifest.read_text())
    if workspace["workspace"]["package"]["version"] != base:
        raise ValueError("Workspace version does not match the upstream base")
    names = set()
    # Cargo also adds local path dependencies as implicit workspace members.
    for member_manifest in (root / "codex-rs").rglob("Cargo.toml"):
        if "target" in member_manifest.relative_to(root / "codex-rs").parts:
            continue
        package = tomllib.loads(member_manifest.read_text()).get("package", {})
        if package.get("version") == {"workspace": True}:
            names.add(package["name"])
    lock_path = root / "codex-rs/Cargo.lock"
    lock = lock_path.read_text()
    blocks = lock.split("[[package]]")
    old_versions = {}
    for index in range(1, len(blocks)):
        package = tomllib.loads("[[package]]" + blocks[index])["package"][0]
        if package["name"] in names and "source" not in package:
            if package["version"] not in {base, "0.0.0"}:
                raise ValueError(f"Unexpected workspace lock version: {package['name']}")
            old_versions[package["name"]] = package["version"]
            blocks[index], count = re.subn(
                rf'^version = "{re.escape(package["version"])}"$', f'version = "{version}"',
                blocks[index], count=1, flags=re.M,
            )
            if count != 1:
                raise ValueError("Cannot update workspace lock version")
    if old_versions.keys() != names:
        raise ValueError(f"Workspace packages missing from lockfile: {sorted(names - old_versions.keys())}")
    lock_text = "[[package]]".join(blocks)
    # Version-qualified references can distinguish a local package from a registry one.
    for name, old_version in old_versions.items():
        lock_text = lock_text.replace(f'"{name} {old_version}"', f'"{name} {version}"')
    manifest_text, count = re.subn(
        rf'(\[workspace\.package\]\s*\nversion = "){re.escape(base)}(")',
        rf'\g<1>{version}\2', manifest.read_text(), count=1,
    )
    if count != 1:
        raise ValueError("Cannot update workspace package version")
    manifest.write_text(manifest_text, encoding="utf-8")
    lock_path.write_text(lock_text, encoding="utf-8")


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
    }
    if "linux" in args.target:
        values["CODEX_BWRAP_SHA256"] = digest(args.package_dir / "codex-resources/bwrap")
    set_workspace_version(ROOT, base, version)
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


def publish(tag: str, directory: Path) -> None:
    _, version = parse_tag(tag)
    archives = [directory / f"codex-package-{target}.tar.gz" for target in TARGETS]
    if any(not path.is_file() for path in archives):
        raise ValueError("All three platform packages are required before publication")
    commit = run("git", "rev-parse", "HEAD")
    verify_tag_commit(tag, commit)
    repository = os.environ["GITHUB_REPOSITORY"]
    (directory / "codex-package_SHA256SUMS").write_text(
        "".join(f"{digest(path)}  {path.name}\n" for path in archives), encoding="utf-8",
    )
    for source in ["install.sh", "install.ps1"]:
        shutil.copyfile(ROOT / "scripts/install" / source, directory / source)
    shutil.copyfile(ROOT / "codex-rs/core/config.schema.json", directory / "config-schema.json")
    existing = github_json(f"repos/{repository}/releases/tags/{tag}", missing_ok=True)
    if existing is not None and not existing["draft"]:
        raise ValueError("Refusing to replace an already published fork release; publish a new commit")
    latest = github_json(f"repos/{repository}/releases/latest", missing_ok=True)
    make_latest = latest is None or should_make_latest(version, latest)
    if latest is not None and make_latest and latest["tag_name"] != tag:
        comparison = github_json(f"repos/{repository}/compare/{latest['tag_name']}...{commit}")
        if comparison["status"] not in {"ahead", "identical", "behind", "diverged"}:
            raise ValueError("Cannot determine release commit ancestry")
        make_latest = comparison["status"] in {"ahead", "identical"}
    notes = directory / "release-notes.md"
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
    if existing is None:
        run("gh", "release", "create", tag, "--repo", repository, "--verify-tag", "--draft", "--latest=false", "--title", version, "--notes-file", str(notes))
    assets = archives + [directory / name for name in ["codex-package_SHA256SUMS", "install.sh", "install.ps1", "config-schema.json"]]
    run("gh", "release", "upload", tag, "--repo", repository, "--clobber", *(str(path) for path in assets))
    run("gh", "release", "edit", tag, "--repo", repository, "--draft=false", "--prerelease=false", f"--latest={str(make_latest).lower()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    resolve_parser = commands.add_parser("resolve")
    resolve_parser.add_argument("--tag", help="Explicit tag; otherwise allocate or resume a release for this commit.")
    resolve_parser.add_argument("--github-output", required=True, type=Path)
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
        resolve(args.tag, args.github_output)
    elif args.command == "prepare":
        prepare(args)
    elif args.command == "assemble":
        print(assemble(args.package_dir, args.binary, args.exec_server_binary, args.output_dir))
    else:
        publish(args.tag, args.directory)


if __name__ == "__main__":
    main()
