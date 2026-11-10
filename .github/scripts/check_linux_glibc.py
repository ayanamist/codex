"""Reject packages whose ELF imports require a glibc newer than 2.38."""

import argparse
import os
from pathlib import Path
import re
import subprocess

MAX_GLIBC = (2, 38)


def required_glibc_versions(output: str) -> set[tuple[int, ...]]:
    """Read imports only; version definitions do not constrain the host libc."""
    in_needs = False
    versions = set()
    for line in output.splitlines():
        if line.startswith("Version "):
            in_needs = line.startswith("Version needs section ")
        if not in_needs:
            continue
        for name in re.findall(r"\bName: (GLIBC_[A-Za-z0-9_.]+)", line):
            # Packed relative relocations are supported since glibc 2.36.
            if name == "GLIBC_ABI_DT_RELR":
                versions.add((2, 36))
            elif re.fullmatch(r"GLIBC_[0-9]+(?:\.[0-9]+)+", name):
                versions.add(tuple(int(part) for part in name[6:].split(".")))
            else:
                raise ValueError(f"unsupported glibc import: {name}")
    return versions


def check_package(package: Path) -> int:
    checked = 0
    failures = []
    for path in sorted(package.rglob("*")):
        if not path.is_file():
            continue
        with path.open("rb") as source:
            if source.read(4) != b"\x7fELF":
                continue
        result = subprocess.run(
            ["readelf", "--version-info", "--wide", str(path)],
            check=True, capture_output=True, text=True,
            env={**os.environ, "LC_ALL": "C"},
        )
        try:
            versions = required_glibc_versions(result.stdout)
            # Pad the ceiling to compare e.g. GLIBC_2.38.0 numerically.
            newer = [version for version in versions if version > MAX_GLIBC + (0,) * (len(version) - 2)]
            if newer:
                required = ".".join(str(part) for part in max(newer))
                raise ValueError(f"requires glibc {required}, maximum allowed is 2.38")
        except ValueError as error:
            failures.append(f"{path.relative_to(package)}: {error}")
        checked += 1
    if checked == 0:
        raise ValueError("package contains no ELF files")
    if failures:
        raise ValueError("\n".join(failures))
    print(f"Checked {checked} ELF files: all glibc imports are compatible with 2.38")
    return checked


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    check_package(args.package)


if __name__ == "__main__":
    main()
