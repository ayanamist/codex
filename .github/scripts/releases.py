"""Validate Codex releases and check whether their GitHub channel pointers can advance."""

import argparse
import json
import re
import sys

_VERSION_RE = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def is_valid_release_version(version: str) -> bool:
    if _VERSION_RE.fullmatch(version) is None:
        return False
    # SemVer forbids leading zeroes in an entirely numeric prerelease identifier.
    base, _, suffix = version.partition("-")
    return all(int(part) <= 2**64 - 1 for part in base.split(".")) and all(
        not (part.isdigit() and len(part) > 1 and part.startswith("0"))
        for part in suffix.split(".")
    )


def is_valid_stable_release_version(version: str) -> bool:
    # Legacy npm/R2 callers lack GitHub's prerelease flag and retain their
    # conventional alpha/beta channel distinction. GitHub uses metadata below.
    channel = version.partition("-")[2].partition(".")[0]
    return is_valid_release_version(version) and channel not in {"alpha", "beta"}


def _version_key(version: str) -> tuple[tuple[int, ...], int, tuple[int, ...] | str]:
    base, _, prerelease = version.partition("-")
    channel, _, suffix = prerelease.partition(".")
    release = tuple(int(part) for part in base.split("."))
    if channel in {"alpha", "beta", "", "ayanamist"} and (
        not suffix or all(part.isdigit() for part in suffix.split("."))
    ):
        return release, {"alpha": 0, "beta": 1, "": 2, "ayanamist": 3}[channel], tuple(
            int(part) for part in suffix.split(".")
        ) if suffix else ()
    return release, 4, prerelease


def should_update_version(version: str, current_version: str) -> bool:
    """Compare channel identities; fork hashes require an authoritative latest pointer.

    Hashes have no chronological order. Publishers must also verify commit ancestry
    before advancing a pointer between different hashes of the same release line.
    """
    if not is_valid_release_version(version):
        raise ValueError(f"invalid release version: {version}")
    if not is_valid_release_version(current_version):
        # Replace an unreadable pointer so publishing can repair it.
        return True

    candidate, current = _version_key(version), _version_key(current_version)
    if candidate[:2] == current[:2] and candidate[1] == 4:
        return candidate[2] != current[2]
    return candidate > current


def should_make_latest(version: str, latest: dict) -> bool:
    if not is_valid_release_version(version):
        raise ValueError(f"expected a valid release version: {version}")
    tag = latest.get("tag_name", "")
    current = tag.removeprefix("rust-v") if isinstance(tag, str) else ""
    if (
        not isinstance(tag, str)
        or not tag.startswith("rust-v")
        or not is_valid_release_version(current)
        or latest.get("draft") is not False
        or latest.get("prerelease") is not False
    ):
        raise ValueError("Cannot determine the current GitHub latest stable release")
    # Suffixes identify builds, not publication order. The fork publisher checks
    # commit ancestry before advancing latest within a base version.
    return _version_key(version)[0] >= _version_key(current)[0]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument(
        "--check-github",
        choices=("latest", "canary"),
        help="Compare with the latest release JSON or canary Cargo.toml on stdin.",
    )
    args = parser.parse_args()
    if args.check_github is None:
        raise SystemExit(0 if is_valid_release_version(args.version) else 1)
    if args.check_github == "latest":
        update = should_make_latest(args.version, json.load(sys.stdin))
    else:
        import tomllib

        try:
            current_version = tomllib.loads(sys.stdin.read())["workspace"]["package"][
                "version"
            ]
        except (tomllib.TOMLDecodeError, KeyError, TypeError):
            current_version = ""
        if not isinstance(current_version, str):
            current_version = ""
        update = should_update_version(args.version, current_version)
    print(str(update).lower())
