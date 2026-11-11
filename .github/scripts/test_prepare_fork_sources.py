import json
from pathlib import Path
import tempfile
import tomllib
import unittest

import prepare_fork_sources as prep


class ForkSourceTests(unittest.TestCase):
    def workspace(self, root):
        (root / "Cargo.toml").write_text(
            '[workspace]\nmembers=["cli", "exec-server-cli", "library", "build-info"]\n'
            '[workspace.package]\nversion="0.167.0"\n'
            '[workspace.dependencies]\ncodex-build-info={path="build-info"}\n'
        )
        packages = [("cli", "codex-cli", "codex"), ("exec-server-cli", "codex-exec-server-cli", "codex-exec-server"), ("library", "example-library", None), ("build-info", "codex-build-info", None)]
        blocks = []
        for directory, name, binary in packages:
            crate = root / directory
            (crate / "src").mkdir(parents=True)
            manifest = f'[package]\nname="{name}"\nversion.workspace=true\n[dependencies]\n'
            if binary:
                manifest += f'[[bin]]\nname="{binary}"\npath="src/main.rs"\n'
            (crate / "Cargo.toml").write_text(manifest)
            (crate / "src" / ("main.rs" if binary else "lib.rs")).write_text('fn main() {}\n' if binary else 'pub fn version() -> &\'static str { env!("CARGO_PKG_VERSION") }\n')
            blocks.append(f'[[package]]\nname="{name}"\nversion="0.0.0"\n')
        blocks.append('[[package]]\nname="external"\nversion="1.2.3"\nsource="registry+example"\nchecksum="unchanged"\n')
        (root / "Cargo.lock").write_text("version=4\n" + "\n".join(blocks))

    def snapshot(self, root):
        return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def test_lexer_preserves_comments_strings_raw_strings_and_lifetimes(self):
        source = '''// env!("CARGO_PKG_VERSION")
/* outer /* env!("CARGO_PKG_VERSION") */ end */
let text = r###"env!("CARGO_PKG_VERSION")"###;
let quoted = "env!(\\\"CARGO_PKG_VERSION\\\")";
let character = '"';
let value: &'static str = env!("CARGO_PKG_VERSION");
'''
        transformed = prep.version_reads(source)
        self.assertEqual(transformed, source.replace('= env!("CARGO_PKG_VERSION");', '= ' + prep.VERSION + ';'))

    def test_qualified_optional_and_component_macros(self):
        source = 'std::env!("CARGO_PKG_VERSION"); option_env!(r"CARGO_PKG_VERSION"); env!("CARGO_PKG_VERSION_MINOR"); clap::crate_version!();'
        transformed = prep.version_reads(source)
        self.assertNotIn("std::codex", transformed)
        self.assertIn("Some(" + prep.VERSION + ")", transformed)
        self.assertIn('.nth(1).unwrap_or("0")', transformed)
        self.assertNotIn("CARGO_PKG_VERSION", transformed)
        self.assertNotIn("crate_version!", transformed)

    def test_concat_becomes_a_runtime_format(self):
        transformed = prep.version_reads('concat!("client/", concat!(env!("CARGO_PKG_VERSION"), "/suffix"))')
        self.assertNotIn("concat!", transformed)
        self.assertIn('format!("{}{}", "client/", format!', transformed)

    def test_clap_only_changes_shorthand_version_attributes(self):
        source = '#[command(name="test", version)]\n#[clap(author, version, about)]\n#[command(version="fixed")]\nlet version = 1;'
        transformed = prep.clap_versions(source)
        self.assertEqual(transformed.count("version = " + prep.VERSION), 2)
        self.assertIn('#[command(version="fixed")]', transformed)

    def test_constant_imports_calls_and_format_capture_are_adapted(self):
        source = 'pub const APP_VERSION: &str = env!("CARGO_PKG_VERSION");'
        source = prep.version_reads(source)
        edits, symbols = prep.constants(source)
        definition = prep.consumers(source, edits, symbols)
        self.assertIn("pub fn app_version()", definition)
        uses = 'use crate::APP_VERSION; fn run() { accept(APP_VERSION); println!("v{APP_VERSION}"); }'
        transformed = prep.consumers(uses, [], symbols)
        self.assertIn('use crate::app_version;', transformed)
        self.assertIn('accept(app_version())', transformed)
        self.assertIn('APP_VERSION = app_version()', transformed)

    def test_grouped_imports_are_supported_and_aliases_fail_explicitly(self):
        symbol = [("APP_VERSION", "app_version", None)]
        self.assertEqual(
            prep.consumers("use crate::version::{APP_VERSION};", [], symbol),
            "use crate::version::{app_version};",
        )
        for source in ["use crate::APP_VERSION as VER;", 'fn f() { let APP_VERSION = "shadow"; }']:
            with self.subTest(source=source), self.assertRaises(ValueError):
                prep.consumers(source, [], symbol)

    def test_local_constants_do_not_rename_other_functions_bindings(self):
        source = 'fn one() { const VERSION: &str = env!("CARGO_PKG_VERSION"); println!("{VERSION}"); } fn two() { let VERSION = "other"; use_value(VERSION); }'
        source = prep.version_reads(source)
        edits, symbols = prep.constants(source)
        transformed = prep.consumers(source, edits, symbols)
        self.assertIn("fn version()", transformed)
        self.assertIn('VERSION = version()', transformed)
        self.assertIn('use_value(VERSION)', transformed)

    def test_unsupported_version_shapes_fail(self):
        for source in ['env!("CARGO_PKG_VERSION_PRE")', 'env!(concat!("CARGO_PKG_", "VERSION"))']:
            with self.subTest(source=source), self.assertRaises(ValueError):
                prep.version_reads(source)
        with self.assertRaisesRegex(ValueError, "Unsupported runtime"):
            prep.constants(prep.version_reads('static V: &str = env!("CARGO_PKG_VERSION");'))
        with self.assertRaisesRegex(ValueError, "Unsupported runtime"):
            prep.constants(prep.version_reads('const V: Option<&str> = option_env!("CARGO_PKG_VERSION");'))

    def test_prepare_is_atomic_idempotent_and_covers_new_source_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.workspace(root)
            before = self.snapshot(root)
            preview = prep.prepare(root, check=True)
            self.assertTrue(preview["files"])
            self.assertEqual(self.snapshot(root), before)
            prep.prepare(root)
            prepared = self.snapshot(root)
            self.assertEqual(tomllib.loads((root / "Cargo.toml").read_text())["workspace"]["package"]["version"], "0.0.0")
            self.assertEqual(prep.prepare(root)["files"], [])
            self.assertEqual(self.snapshot(root), prepared)
            packages = tomllib.loads((root / "Cargo.lock").read_text())["package"]
            self.assertEqual(next(p for p in packages if p["name"] == "external"), {"name": "external", "version": "1.2.3", "source": "registry+example", "checksum": "unchanged"})
            self.assertTrue(all(p["version"] == "0.0.0" for p in packages if "source" not in p))
            new = root / "library/src/new_upstream.rs"
            new.write_text('pub fn new_version() -> &\'static str { env!("CARGO_PKG_VERSION") }')
            report = prep.prepare(root)
            self.assertIn("library/src/new_upstream.rs", report["files"])
            self.assertIn(prep.VERSION, new.read_text())
            self.assertEqual((root / "build-info/src/lib.rs").read_bytes(), before[Path("build-info/src/lib.rs")])

    def test_normalizes_local_lock_identities_and_qualified_references_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.workspace(root)
            lock = root / "Cargo.lock"
            text = lock.read_text().replace(
                'name="example-library"\nversion="0.0.0"',
                'name="example-library"\nversion="0.167.0"',
            ).replace(
                'name="codex-cli"\nversion="0.0.0"',
                'name="codex-cli"\nversion="0.0.0"\ndependencies = [\n "example-library 0.167.0",\n]',
            )
            lock.write_text(text)
            external = next(p for p in tomllib.loads(text)["package"] if "source" in p)
            prep.prepare(root)
            packages = tomllib.loads(lock.read_text())["package"]
            self.assertTrue(all(p["version"] == "0.0.0" for p in packages if "source" not in p))
            cli = next(p for p in packages if p["name"] == "codex-cli")
            self.assertIn("example-library 0.0.0", cli["dependencies"])
            self.assertEqual(next(p for p in packages if "source" in p), external)

    def test_unsupported_new_code_leaves_every_file_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.workspace(root)
            (root / "library/src/unsupported.rs").write_text('static VERSION: &str = env!("CARGO_PKG_VERSION");')
            before = self.snapshot(root)
            with self.assertRaisesRegex(ValueError, "unsupported.rs"):
                prep.prepare(root)
            self.assertEqual(self.snapshot(root), before)

    def test_unknown_macro_alias_or_runtime_read_cannot_be_silently_skipped(self):
        for expression in ['cargo_env!("CARGO_PKG_VERSION")', 'std::env::var("CARGO_PKG_VERSION")']:
            with self.subTest(expression=expression), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.workspace(root)
                (root / "library/src/new_syntax.rs").write_text(f"fn f() {{ let _ = {expression}; }}")
                before = self.snapshot(root)
                with self.assertRaisesRegex(ValueError, "Unconverted Cargo"):
                    prep.prepare(root)
                self.assertEqual(self.snapshot(root), before)


if __name__ == "__main__":
    unittest.main()
