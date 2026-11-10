import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import tomllib
import unittest

import prepare_rusty_v8_source as source


class PrepareRustyV8SourceTests(unittest.TestCase):
    def fixture(self, root, *, extra=(), missing=()):
        workspace = root / "workspace"
        (workspace / ".cargo").mkdir(parents=True)
        (workspace / ".cargo/config.toml").write_text('[env]\nEXISTING_FLAG = "keep"\n')
        revision = "a" * 40
        repository = "https://github.com/example/rusty_v8.git"
        (workspace / "Cargo.toml").write_text(
            f'[patch.crates-io]\nv8 = {{ git = "{repository}", rev = "{revision}" }}\n'
        )
        (workspace / "Cargo.lock").write_text(
            f'[[package]]\nname = "v8"\nversion = "1.2.3"\n'
            f'source = "git+{repository}?rev={revision}#{revision}"\n'
        )
        archive = root / "source.tar.gz"
        contents = {
            "Cargo.toml": b'[package]\nname = "v8"\nversion = "1.2.3"\n',
            "src/lib.rs": b"pub fn binding() {}\n",
            "src/binding.rs": b'include!(env!("RUSTY_V8_SRC_BINDING_PATH"));\n',
            "build.rs": b"fn main() {}\n",
            ".gitmodules": b'[submodule "v8"]\npath = v8\n',
        }
        with tarfile.open(archive, "w:gz") as output:
            for name, content in contents.items():
                if name in missing:
                    continue
                member = tarfile.TarInfo(f"rusty_v8-{revision}/{name}")
                member.size = len(content)
                output.addfile(member, io.BytesIO(content))
            for member in extra:
                output.addfile(member, io.BytesIO(b""))
        pins = root / "pins"
        pins.mkdir()
        pin = {"repository": repository, "revision": revision, "version": "1.2.3", "archiveSha256": source.digest(archive)}
        (pins / "rusty_v8_1_2_3_source.json").write_text(json.dumps(pin))
        return workspace, root / "vendor", archive, pins, contents

    def test_snapshot_preserves_source_identity_and_configures_prebuilt_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace, vendor, archive, pins, contents = self.fixture(Path(temporary))
            originals = {name: (workspace / name).read_bytes() for name in ["Cargo.toml", "Cargo.lock"]}
            source.prepare(workspace, vendor, archive=archive, pins=pins)
            for name, original in originals.items():
                self.assertEqual((workspace / name).read_bytes(), original)
            package = vendor / "v8-1.2.3"
            for name, content in contents.items():
                self.assertEqual((package / name).read_bytes(), content)
            checksums = json.loads((package / ".cargo-checksum.json").read_text())
            self.assertIsNone(checksums["package"])
            self.assertEqual(checksums["files"], {name: hashlib.sha256(content).hexdigest() for name, content in contents.items()})
            config = tomllib.loads((workspace / ".cargo/config.toml").read_text())
            self.assertEqual(config["env"]["EXISTING_FLAG"], "keep")
            self.assertEqual(config["env"]["V8_FROM_SOURCE"], {"value": "0", "force": True})
            self.assertEqual(config["source"][source.VENDOR_NAME]["directory"], "../vendor")
            self.assertFalse((package / "v8").exists())

    def test_archive_checksum_failure_leaves_workspace_and_destination_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace, vendor, archive, pins, _ = self.fixture(Path(temporary))
            config = (workspace / ".cargo/config.toml").read_bytes()
            archive.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                source.prepare(workspace, vendor, archive=archive, pins=pins)
            self.assertFalse(vendor.exists())
            self.assertEqual((workspace / ".cargo/config.toml").read_bytes(), config)

    def test_patch_or_lock_drift_requires_a_matching_source_pin(self):
        for name in ["Cargo.toml", "Cargo.lock"]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                workspace, vendor, archive, pins, _ = self.fixture(Path(temporary))
                path = workspace / name
                path.write_text(path.read_text().replace("a" * 40, "b" * 40))
                with self.assertRaisesRegex(ValueError, "match both"):
                    source.prepare(workspace, vendor, archive=archive, pins=pins)
                self.assertFalse(vendor.exists())

    def test_archive_rejects_escaping_paths_links_and_duplicates(self):
        for name, kind in [
            ("../outside", tarfile.REGTYPE),
            ("/absolute", tarfile.REGTYPE),
            ("rusty_v8-" + "a" * 40 + "/linked", tarfile.SYMTYPE),
            ("rusty_v8-" + "a" * 40 + "/Cargo.toml", tarfile.REGTYPE),
        ]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                member = tarfile.TarInfo(name)
                member.type = kind
                member.linkname = "../outside" if kind == tarfile.SYMTYPE else ""
                workspace, vendor, archive, pins, _ = self.fixture(Path(temporary), extra=[member])
                with self.assertRaises(ValueError):
                    source.prepare(workspace, vendor, archive=archive, pins=pins)
                self.assertFalse(vendor.exists())

    def test_required_prebuilt_sources_must_exist(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace, vendor, archive, pins, _ = self.fixture(Path(temporary), missing=["src/binding.rs"])
            with self.assertRaisesRegex(ValueError, "Missing V8 source"):
                source.prepare(workspace, vendor, archive=archive, pins=pins)

    def test_existing_vendor_or_source_configuration_is_not_overwritten(self):
        for conflict in ["vendor", "source", "env"]:
            with self.subTest(conflict=conflict), tempfile.TemporaryDirectory() as temporary:
                workspace, vendor, archive, pins, _ = self.fixture(Path(temporary))
                config = workspace / ".cargo/config.toml"
                if conflict == "vendor":
                    vendor.mkdir()
                    (vendor / "keep").write_text("user data")
                elif conflict == "source":
                    config.write_text(config.read_text() + f"\n[source.{source.SOURCE_NAME}]\ngit = \"existing\"\n")
                else:
                    config.write_text('[env]\nV8_FROM_SOURCE = "1"\n')
                before = config.read_bytes()
                with self.assertRaises(ValueError):
                    source.prepare(workspace, vendor, archive=archive, pins=pins)
                self.assertEqual(config.read_bytes(), before)
                if conflict == "vendor":
                    self.assertEqual((vendor / "keep").read_text(), "user data")

    def test_cargo_builds_locked_git_identity_without_fetching_git(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace, vendor, archive, pins, _ = self.fixture(root)
            manifest = workspace / "Cargo.toml"
            manifest.write_text(manifest.read_text() + (
                '\n[package]\nname = "fixture-app"\nversion = "0.1.0"\nedition = "2021"\n'
                '\n[dependencies]\nv8 = "=1.2.3"\n'
            ))
            lock = workspace / "Cargo.lock"
            lock.write_text('version = 4\n' + lock.read_text() + (
                '\n[[package]]\nname = "fixture-app"\nversion = "0.1.0"\ndependencies = ["v8"]\n'
            ))
            (workspace / "src").mkdir()
            (workspace / "src/main.rs").write_text("fn main() { v8::binding(); }\n")
            original_manifest, original_lock = manifest.read_bytes(), lock.read_bytes()
            source.prepare(workspace, vendor, archive=archive, pins=pins)
            home = root / "cargo-home"
            environment = {**os.environ, "CARGO_HOME": str(home), "CARGO_TARGET_DIR": str(root / "target")}
            command = ["cargo", "check", "--locked", "--offline"]
            result = subprocess.run(command, cwd=workspace, env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(manifest.read_bytes(), original_manifest)
            self.assertEqual(lock.read_bytes(), original_lock)
            self.assertFalse((home / "git").exists())
            # Force Cargo to reread the source, proving directory checksums are enforced.
            (vendor / "v8-1.2.3/src/lib.rs").write_text("pub fn binding() { panic!(); }\n")
            subprocess.run(["cargo", "clean"], cwd=workspace, env=environment, check=True, capture_output=True)
            result = subprocess.run(command, cwd=workspace, env=environment, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("checksum", result.stderr)


if __name__ == "__main__":
    unittest.main()
