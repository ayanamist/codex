"""Adapt application version reads in a disposable build checkout.

No release version is substituted into source: the generated library code is
identical across releases. Only the executable's build-info macro reads the
changing release stamp. Plan every edit and reject unsupported version reads
before writing any files. Comments and string contents are never searched as code.
"""

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[2]
VERSION = "codex_build_info::application_version()"
PAIRS = {"(": ")", "[": "]", "{": "}"}
RAW = re.compile(r'(?:br|cr|r)(#*)"')
QUOTED = re.compile(r'(?:b|c)?"')
WORD = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
CHAR = re.compile(r"'(?:\\(?:u\{[0-9a-fA-F_]+\}|x[0-9a-fA-F]{2}|.)|[^'\\\n])'")
FORMAT_MACROS = {"format", "print", "println", "eprint", "eprintln", "write", "writeln", "panic", "assert", "assert_eq", "assert_ne"}


@dataclass
class Token:
    value: str
    start: int
    end: int
    kind: str = "code"


def tokens(source: str) -> list[Token]:
    result = []
    pos = 0
    while pos < len(source):
        start = pos
        if source[pos].isspace():
            pos += 1
            continue
        if source.startswith("//", pos):
            end = source.find("\n", pos)
            pos = len(source) if end < 0 else end
            continue
        if source.startswith("/*", pos):
            pos += 2
            depth = 1
            while depth and pos < len(source):
                if source.startswith("/*", pos):
                    depth += 1
                    pos += 2
                elif source.startswith("*/", pos):
                    depth -= 1
                    pos += 2
                else:
                    pos += 1
            if depth:
                raise ValueError("Unterminated Rust block comment")
            continue
        raw = RAW.match(source, pos)
        if raw:
            closing = '"' + raw[1]
            end = source.find(closing, pos + len(raw[0]))
            if end < 0:
                raise ValueError("Unterminated Rust raw string")
            pos = end + len(closing)
            result.append(Token(source[start:pos], start, pos, "string"))
            continue
        quoted = QUOTED.match(source, pos)
        if quoted:
            pos += len(quoted[0])
            while pos < len(source):
                if source[pos] == "\\":
                    pos += 2
                elif source[pos] == '"':
                    pos += 1
                    break
                else:
                    pos += 1
            result.append(Token(source[start:pos], start, pos, "string"))
            continue
        char = CHAR.match(source, pos)
        if char:
            pos += len(char[0])
            result.append(Token(source[start:pos], start, pos, "char"))
            continue
        word = WORD.match(source, pos)
        pos += len(word[0]) if word else 1
        result.append(Token(source[start:pos], start, pos))
    return result


def closing(ts: list[Token], index: int) -> int:
    stack = [PAIRS[ts[index].value]]
    for end in range(index + 1, len(ts)):
        value = ts[end].value
        if ts[end].kind != "code":
            continue
        if value in PAIRS:
            stack.append(PAIRS[value])
        elif value in PAIRS.values():
            if not stack or stack.pop() != value:
                raise ValueError("Unbalanced Rust delimiters")
            if not stack:
                return end
    raise ValueError("Unclosed Rust delimiter")


def macros(ts: list[Token], names: set[str]) -> list[tuple[int, int, int]]:
    result = []
    for index in range(len(ts) - 2):
        if ts[index].kind == "code" and ts[index].value in names and ts[index + 1].value == "!" and ts[index + 2].value in PAIRS:
            result.append((index, index + 2, closing(ts, index + 2)))
    return result


def apply(source: str, edits: list[tuple[int, int, str]]) -> str:
    boundary = len(source)
    for start, end, replacement in sorted(edits, reverse=True):
        if end > boundary:
            raise ValueError("Overlapping source edits")
        source = source[:start] + replacement + source[end:]
        boundary = start
    return source


def literal(token: Token) -> str:
    if token.value.startswith('r'):
        match = re.fullmatch(r'r(#*)"(.*)"\1', token.value, re.S)
        return match[2] if match else ""
    try:
        return json.loads(token.value)
    except (ValueError, TypeError):
        return ""


def version_reads(source: str) -> str:
    if not re.search(r"\b(?:env|option_env|crate_version)\s*!", source):
        return source
    ts = tokens(source)
    edits = []
    for index, opening, end in macros(ts, {"env", "option_env", "crate_version"}):
        name = ts[index].value
        args = ts[opening + 1:end]
        if name == "crate_version":
            if args:
                raise ValueError("Unsupported crate_version! arguments")
            expression = VERSION
        else:
            key = literal(args[0]) if args and args[0].kind == "string" else ""
            if not key.startswith("CARGO_PKG_VERSION"):
                combined = "".join(literal(token) for token in args if token.kind == "string")
                if "CARGO_PKG_VERSION" in combined:
                    raise ValueError("Version env! must use a literal Cargo key")
                continue
            if key == "CARGO_PKG_VERSION":
                expression = VERSION
            elif key in {"CARGO_PKG_VERSION_MAJOR", "CARGO_PKG_VERSION_MINOR", "CARGO_PKG_VERSION_PATCH"}:
                component = ["MAJOR", "MINOR", "PATCH"].index(key.rsplit("_", 1)[1])
                expression = f'{VERSION}.split([\'.\', \'-\', \'+\']).nth({component}).unwrap_or("0")'
            else:
                raise ValueError(f"Unsupported Cargo version field: {key}")
            if name == "option_env":
                expression = f"Some({expression})"
        start = index
        while start >= 3 and ts[start - 1].value == ts[start - 2].value == ":" and re.fullmatch(r"\w+", ts[start - 3].value):
            start -= 3
        edits.append((ts[start].start, ts[end].end, expression))
    source = apply(source, edits)
    # Lower only concat! expressions which became runtime version expressions.
    while True:
        ts = tokens(source)
        candidates = [call for call in macros(ts, {"concat"}) if VERSION in source[ts[call[1]].end:ts[call[2]].start]]
        if not candidates:
            return source
        index, opening, end = candidates[-1]
        args = []
        start = opening + 1
        cursor = start
        while cursor < end:
            if ts[cursor].value in PAIRS:
                cursor = closing(ts, cursor) + 1
                continue
            if ts[cursor].value == ",":
                args.append(source[ts[start].start:ts[cursor].start].strip())
                start = cursor + 1
            cursor += 1
        if start < end:
            args.append(source[ts[start].start:ts[end].start].strip())
        expression = f'format!("{"{}" * len(args)}", {", ".join(args)})'
        source = apply(source, [(ts[index].start, ts[end].end, expression)])


def functions(ts: list[Token]) -> list[tuple[int, int]]:
    result = []
    for index, token in enumerate(ts):
        if token.value != "fn" or token.kind != "code":
            continue
        cursor = index + 1
        while cursor < len(ts) and ts[cursor].value not in {"(", ";", "{"}:
            cursor += 1
        if cursor == len(ts) or ts[cursor].value != "(":
            continue
        cursor = closing(ts, cursor) + 1
        while cursor < len(ts) and ts[cursor].value not in {"{", ";"}:
            cursor += 1
        if cursor < len(ts) and ts[cursor].value == "{":
            result.append((ts[cursor].start, ts[closing(ts, cursor)].end))
    return result


def constants(source: str) -> tuple[list[tuple[int, int, str]], list[tuple[str, str, tuple[int, int] | None]]]:
    if VERSION not in source:
        return [], []
    ts = tokens(source)
    scopes = functions(ts)
    edits, symbols = [], []
    for index, token in enumerate(ts):
        if token.value not in {"const", "static"} or token.kind != "code" or index + 2 >= len(ts) or ts[index + 2].value != ":":
            continue
        if index and ts[index - 1].value in {"<", ","}:
            continue  # A const generic parameter, not an item initializer.
        cursor = index + 3
        while cursor < len(ts) and ts[cursor].value not in {"=", ";", "{", "}"}:
            cursor += 1
        if cursor == len(ts) or ts[cursor].value != "=":
            continue
        equals = cursor
        cursor += 1
        while cursor < len(ts) and ts[cursor].value != ";":
            cursor = closing(ts, cursor) + 1 if ts[cursor].value in PAIRS else cursor + 1
        if cursor == len(ts):
            continue
        expression = source[ts[equals].end:ts[cursor].start].strip()
        if VERSION not in expression:
            continue
        type_name = "".join(t.value for t in ts[index + 3:equals])
        if token.value != "const" or type_name not in {"&str", "&'staticstr"}:
            raise ValueError("Unsupported runtime version in const/static initializer")
        old = ts[index + 1].value
        new = old.lower()
        scope = next((scope for scope in reversed(scopes) if scope[0] < token.start < scope[1]), None)
        if "format!" in expression:
            body = f"static VALUE: std::sync::OnceLock<String> = std::sync::OnceLock::new(); VALUE.get_or_init(|| {expression})"
        else:
            body = expression
        edits.append((token.start, ts[cursor].end, f"fn {new}() -> &'static str {{ {body} }}"))
        symbols.append((old, new, scope))
    return edits, symbols


def consumers(source: str, definitions: list, symbols: list) -> str:
    if not definitions and not any(old in source for old, _, _ in symbols):
        return source
    ts = tokens(source)
    edits = list(definitions)
    format_args = {}
    format_calls = macros(ts, FORMAT_MACROS)
    imports = []
    for i, token in enumerate(ts):
        if token.value == "use" and token.kind == "code":
            end = next((j for j in range(i + 1, len(ts)) if ts[j].value == ";"), None)
            if end is not None:
                imports.append((i, end))
    for index, token in enumerate(ts):
        if any(start <= token.start < end for start, end, _ in definitions):
            continue
        applicable = {old: new for old, new, scope in symbols if scope is None or scope[0] < token.start < scope[1]}
        if token.kind == "string":
            for old, new in applicable.items():
                if re.search(r"(?<!\{)\{" + old + r"(?:\}|:|!)", token.value):
                    call = next((call for call in reversed(format_calls) if ts[call[1]].start < token.start < ts[call[2]].end), None)
                    if call is None:
                        continue
                    format_args.setdefault(call[2], {})[old] = new
            continue
        if token.value not in applicable:
            continue
        # Support both flat imports and grouped use trees without adding calls.
        imported = next(((start, end) for start, end in imports if start < index < end), None)
        importing = imported is not None
        if importing and any(t.value == "as" for t in ts[imported[0]:imported[1]]):
            raise ValueError("Version constant import aliases need explicit handling")
        if index and ts[index - 1].value in {"let", "mut"}:
            raise ValueError("A version constant is shadowed by a local binding")
        if not importing and index + 1 < len(ts) and ts[index + 1].value == "=":
            # Keep explicit named format arguments, e.g. VERSION = expression.
            continue
        edits.append((token.start, token.end, applicable[token.value] + ("" if importing else "()")))
    for end, names in format_args.items():
        opening = next(opening for _, opening, call_end in format_calls if call_end == end)
        explicit = {ts[i].value for i in range(opening + 1, end - 1) if ts[i + 1].value == "="}
        args = [f"{old} = {new}()" for old, new in names.items() if old not in explicit]
        if args:
            separator = " " if ts[end - 1].value == "," else ", "
            edits.append((ts[end].start, ts[end].start, separator + ", ".join(args)))
    return apply(source, edits)


def clap_versions(source: str) -> str:
    if "version" not in source or not re.search(r"#\s*\[\s*(?:command|clap)\b", source):
        return source
    ts = tokens(source)
    edits = []
    for index in range(len(ts) - 4):
        if [t.value for t in ts[index:index + 2]] != ["#", "["] or ts[index + 2].value not in {"clap", "command"} or ts[index + 3].value != "(":
            continue
        end = closing(ts, index + 3)
        cursor = index + 4
        while cursor < end:
            if ts[cursor].value == "version" and (cursor == index + 4 or ts[cursor - 1].value == ",") and ts[cursor + 1].value in {",", ")"}:
                edits.append((ts[cursor].start, ts[cursor].end, "version = " + VERSION))
            cursor = closing(ts, cursor) + 1 if ts[cursor].value in PAIRS else cursor + 1
    return apply(source, edits)


def audit_version_reads(source: str) -> None:
    if "CARGO_PKG_VERSION" not in source:
        return
    for token in tokens(source):
        if token.kind == "string" and literal(token).startswith("CARGO_PKG_VERSION"):
            raise ValueError("Unconverted Cargo version key; review this version-reading syntax")


def prepare(workspace: Path, *, check: bool = False) -> dict:
    workspace = workspace.resolve()
    manifest = tomllib.loads((workspace / "Cargo.toml").read_text())
    original_version = manifest["workspace"]["package"]["version"]
    root_text = (workspace / "Cargo.toml").read_text()
    root_normalized = root_text
    if original_version != "0.0.0":
        root_normalized, count = re.subn(
            r'(?m)(\[workspace\.package\][^\[]*?^\s*version\s*=\s*["\'])' + re.escape(original_version) + r'(["\'])',
            r'\g<1>0.0.0\2', root_text, count=1,
        )
        if count != 1 or tomllib.loads(root_normalized)["workspace"]["package"]["version"] != "0.0.0":
            raise ValueError("Cannot normalize the workspace version")
    plans, owners, definitions, global_symbols = {}, {}, {}, {}
    paths = []
    for directory, dirs, files in os.walk(workspace):
        dirs[:] = [name for name in dirs if name not in {"target", ".git", ".cache"}]
        paths.extend(Path(directory) / name for name in files if name.endswith(".rs"))
    for path in sorted(paths):
        owner = path.parent
        while owner != workspace and not (owner / "Cargo.toml").exists():
            owner = owner.parent
        if owner == workspace or owner == workspace / "build-info":
            continue
        original = path.read_text()
        try:
            source = clap_versions(version_reads(original))
            edits, symbols = constants(source)
            audit_version_reads(source)
        except ValueError as error:
            raise ValueError(f"{path.relative_to(workspace)}: {error}") from error
        plans[path] = (original, source, symbols)
        owners[path] = owner
        definitions[path] = edits
        for old, new, scope in symbols:
            if scope is None:
                global_symbols.setdefault(owner, set()).add((old, new, None))
    changes, packages = {}, set()
    if root_normalized != root_text:
        changes[workspace / "Cargo.toml"] = root_normalized
    for path, (original, source, symbols) in plans.items():
        try:
            source = consumers(source, definitions[path], sorted(global_symbols.get(owners[path], set())) + [symbol for symbol in symbols if symbol[2] is not None])
        except ValueError as error:
            raise ValueError(f"{path.relative_to(workspace)}: {error}") from error
        if source != original:
            changes[path] = source
        if "codex_build_info::" in source:
            packages.add(owners[path])
    # Resolve the release executable entry points from manifests, not fixed paths.
    found = set()
    for owner in {owner for owner in owners.values()}:
        package = tomllib.loads((owner / "Cargo.toml").read_text())
        for binary in package.get("bin", []):
            if binary["name"] not in {"codex", "codex-exec-server"}:
                continue
            path = owner / binary.get("path", "src/main.rs")
            source = changes.get(path, path.read_text())
            ts = tokens(source)
            main = next((i for i in range(len(ts) - 1) if ts[i].value == "fn" and ts[i + 1].value == "main"), None)
            if main is None:
                raise ValueError(f"Missing main for {binary['name']}")
            opening = next(i for i in range(main, len(ts)) if ts[i].value == "{")
            prefix = [t.value for t in ts[opening + 1:opening + 8]]
            if prefix != ["codex_build_info", ":", ":", "initialize", "!", "(", ")"]:
                if ts[opening + 1].value == "#":
                    raise ValueError(f"Unsupported attributes at entry point: {path}")
                source = apply(source, [(ts[opening].end, ts[opening].end, "\n    codex_build_info::initialize!();")])
                changes[path] = source
            packages.add(owner)
            found.add(binary["name"])
    if found != {"codex", "codex-exec-server"}:
        raise ValueError("Expected both release executable entry points")
    inherited = set()
    for owner in set(owners.values()) | {workspace / "build-info"}:
        package = tomllib.loads((owner / "Cargo.toml").read_text()).get("package", {})
        if package.get("version") == {"workspace": True}:
            inherited.add(package["name"])
    names = set()
    for owner in packages:
        path = owner / "Cargo.toml"
        original = path.read_text()
        package = tomllib.loads(original)
        names.add(package["package"]["name"])
        if "codex-build-info" not in package.get("dependencies", {}):
            if "[dependencies]\n" not in original:
                raise ValueError(f"Missing dependency section: {path}")
            changes[path] = original.replace("[dependencies]\n", "[dependencies]\ncodex-build-info = { workspace = true }\n", 1)
    path = workspace / "Cargo.lock"
    original = path.read_text()
    blocks = original.split("[[package]]")
    old_versions = {}
    for index in range(1, len(blocks)):
        package = tomllib.loads("[[package]]" + blocks[index])["package"][0]
        if "source" not in package and package["name"] in inherited and package["version"] != "0.0.0":
            old_versions[package["name"]] = package["version"]
            blocks[index] = re.sub(r'^version\s*=\s*["\'][^"\']+["\']', 'version = "0.0.0"', blocks[index], count=1, flags=re.M)
        if "source" not in package and package["name"] in names and "codex-build-info" not in package.get("dependencies", []):
            dependencies = sorted(package.get("dependencies", []) + ["codex-build-info"])
            replacement = "dependencies = [\n" + "".join(f' "{name}",\n' for name in dependencies) + "]"
            if "dependencies = [" in blocks[index]:
                blocks[index] = re.sub(r"dependencies = \[\n.*?\n\]", replacement, blocks[index], count=1, flags=re.S)
            else:
                blocks[index] += replacement + "\n"
    lock = "[[package]]".join(blocks)
    for name, version in old_versions.items():
        lock = lock.replace(f'"{name} {version}"', f'"{name} 0.0.0"')
    if lock != original:
        changes[path] = lock
    report = {"files": sorted(str(path.relative_to(workspace)) for path in changes), "packages": sorted(names)}
    if not check:
        for path, source in changes.items():
            path.write_text(source)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=ROOT / "codex-rs")
    parser.add_argument("--check", action="store_true", help="Validate and report planned edits without writing files.")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = prepare(args.workspace, check=args.check)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{'Would adapt' if args.check else 'Adapted'} {len(report['files'])} files in {len(report['packages'])} packages; internal packages normalized to 0.0.0")
