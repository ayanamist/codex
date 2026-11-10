import argparse
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import fork_release as release
from releases import is_valid_stable_release_version, should_make_latest, should_update_version


class ForkReleaseTests(unittest.TestCase):
    def reference(self, commit, kind="commit"):
        return {"object": {"type": kind, "sha": commit}}

    def test_push_reserves_a_tag_with_eight_commit_characters(self):
        commit = "b" * 40
        with patch.dict("os.environ", {"GITHUB_REPOSITORY": "ayanamist/codex"}), patch(
            "fork_release.github_json", side_effect=[{"object": {"sha": commit}}, None, {}]
        ) as api:
            self.assertEqual(release.automatic_tag("0.167.0", commit), ("rust-v0.167.0-fork.bbbbbbbb", True))
        self.assertEqual(api.call_args.kwargs["data"], {
            "ref": "refs/tags/rust-v0.167.0-fork.bbbbbbbb", "sha": commit,
        })
        self.assertEqual(release.commit_tag("0.168.0", commit), "rust-v0.168.0-fork.bbbbbbbb")

    def test_retry_reuses_the_same_commit_tag_or_skips_its_published_release(self):
        commit = "b" * 40
        for existing, should_publish in [(None, True), ({"draft": True}, True), ({"draft": False}, False)]:
            with self.subTest(existing=existing), patch.dict("os.environ", {"GITHUB_REPOSITORY": "ayanamist/codex"}), patch(
                "fork_release.github_json", side_effect=[{"object": {"sha": commit}}, self.reference(commit), existing]
            ) as api:
                self.assertEqual(release.automatic_tag("0.167.0", commit), ("rust-v0.167.0-fork.bbbbbbbb", should_publish))
                self.assertFalse(any(call.kwargs.get("data") for call in api.call_args_list))

    def test_abbreviated_hash_collision_cannot_reuse_another_commit_tag(self):
        commit = "b" * 40
        with patch.dict("os.environ", {"GITHUB_REPOSITORY": "ayanamist/codex"}), patch(
            "fork_release.github_json", side_effect=[{"object": {"sha": commit}}, self.reference("b" * 8 + "c" * 32)]
        ) as api, self.assertRaisesRegex(ValueError, "collision"):
            release.automatic_tag("0.167.0", commit)
        self.assertFalse(any(call.kwargs.get("data") for call in api.call_args_list))

    def test_annotated_tags_are_peeled_before_matching_the_commit(self):
        commit = "b" * 40
        with patch.dict("os.environ", {"GITHUB_REPOSITORY": "ayanamist/codex"}), patch(
            "fork_release.github_json", side_effect=[
                {"object": {"sha": commit}}, self.reference("a" * 40, kind="tag"),
                {"object": {"type": "commit", "sha": commit}}, None,
            ]
        ):
            self.assertEqual(release.automatic_tag("0.167.0", commit), ("rust-v0.167.0-fork.bbbbbbbb", True))

    def test_superseded_code_push_does_not_reserve_a_tag(self):
        with patch.dict("os.environ", {"GITHUB_REPOSITORY": "ayanamist/codex"}), patch(
            "fork_release.github_json", return_value={"object": {"sha": "c" * 40}}
        ) as api, patch("fork_release.run"), patch("fork_release.only_documentation_changed", return_value=False):
            self.assertEqual(release.automatic_tag("0.167.0", "b" * 40), ("", False))
            self.assertEqual(api.call_count, 1)

    def test_later_documentation_push_does_not_cancel_the_pending_code_release(self):
        commit, head = "b" * 40, "c" * 40
        with patch.dict("os.environ", {"GITHUB_REPOSITORY": "ayanamist/codex"}), patch(
            "fork_release.github_json", side_effect=[{"object": {"sha": head}}, None, {}]
        ), patch("fork_release.run") as run, patch("fork_release.only_documentation_changed", return_value=True) as changed:
            self.assertEqual(release.automatic_tag("0.167.0", commit), ("rust-v0.167.0-fork.bbbbbbbb", True))
        changed.assert_called_once_with(commit, head)
        self.assertEqual(run.call_args.args[-1], head)

    def test_documentation_filter_uses_real_git_diffs_and_preserves_code_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def git(*args):
                return release.run("git", *args, cwd=root)
            def commit():
                git("add", ".")
                git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "fixture")
                return git("rev-parse", "HEAD")
            git("init", "-q")
            (root / "main.py").write_text("pass\n")
            base = commit()
            for name in ["README.md", "nested/notes.md", "docs/diagram.svg", "nested/a.mdx", "a.rst", "a.adoc", "a.mmd"]:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("documentation\n")
            docs = commit()
            self.assertTrue(release.only_documentation_changed(base, docs, cwd=root))
            self.assertFalse(release.only_documentation_changed(docs, base, cwd=root))
            (root / "fixture.txt").write_text("runtime input\n")
            code = commit()
            self.assertFalse(release.only_documentation_changed(base, code, cwd=root))
            self.assertFalse(release.only_documentation_changed(docs, code, cwd=root))

    def test_suffix_validation_does_not_restrict_names_or_lengths(self):
        for suffix in ["fork.5d0840ed", "fork.a", "fork." + "a" * 40, "custom-build.abc123", "rc.1", "alpha.1.2.3"]:
            with self.subTest(suffix=suffix):
                self.assertEqual(release.parse_tag("rust-v0.167.0-" + suffix), ("0.167.0", "0.167.0-" + suffix))
        for suffix in ["", "fork..abc", "fork.01", "bad/path", "a b", "a\n"]:
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                release.parse_tag("rust-v0.167.0-" + suffix)
        with self.assertRaisesRegex(ValueError, "leading zeroes"):
            release.commit_tag("0.167.0", "01234567" + "a" * 32)
        with self.assertRaisesRegex(ValueError, "does not match"):
            release.verify_tag_commit("rust-v0.167.0-fork.aaaaaaaa", "b" * 40)

    def test_resolve_exports_the_automatic_tag_for_the_same_workflow(self):
        commit, upstream = "b" * 40, "a" * 40
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "outputs"
            with patch("fork_release.github_json", return_value={"tag_name": "rust-v0.167.0", "draft": False, "prerelease": False}), patch(
                "fork_release.run", side_effect=["", upstream, "", commit]
            ), patch("fork_release.automatic_tag", return_value=("rust-v0.167.0-fork.bbbbbbbb", True)):
                release.resolve(None, output)
            values = dict(line.split("=", 1) for line in output.read_text().splitlines())
            self.assertEqual(values["tag"], "rust-v0.167.0-fork.bbbbbbbb")
            self.assertEqual(values["fork_commit"], commit)
            self.assertEqual(values["upstream_commit"], upstream)
            self.assertEqual(values["should_publish"], "true")

    def test_tag_creation_sends_a_structured_json_body(self):
        import subprocess
        result = subprocess.CompletedProcess([], 0, "{}", "")
        with patch("fork_release.subprocess.run", return_value=result) as run:
            body = {"ref": "refs/tags/rust-v0.167.0-fork.bbbbbbbb", "sha": "b" * 40}
            release.github_json("repos/ayanamist/codex/git/refs", data=body)
            self.assertEqual(json.loads(run.call_args.kwargs["input"]), body)
            self.assertEqual(run.call_args.args[0][-4:], ["--method", "POST", "--input", "-"])

    def test_fork_versions_advance_without_rolling_back_upstream_base(self):
        self.assertTrue(is_valid_stable_release_version("0.167.0-fork.5d0840ed"))
        self.assertTrue(should_update_version("0.167.0-fork.aaaaaaaa", "0.167.0-fork.bbbbbbbb"))
        self.assertTrue(should_update_version("0.167.0-fork.bbbbbbbb", "0.167.0-fork.aaaaaaaa"))
        self.assertFalse(should_update_version("0.167.0-fork.aaaaaaaa", "0.167.0-fork.aaaaaaaa"))
        self.assertTrue(should_update_version("0.167.0-fork.5d0840ed", "0.167.0-ayanamist.2"))
        self.assertFalse(should_update_version("0.167.0-ayanamist.2", "0.167.0-fork.5d0840ed"))
        self.assertTrue(should_update_version("0.167.0-ayanamist.10", "0.167.0-ayanamist.2"))
        self.assertTrue(should_update_version("0.168.0-fork.aaaaaaaa", "0.167.0-fork.bbbbbbbb"))
        self.assertFalse(should_make_latest("0.167.0-fork.bbbbbbbb", {
            "tag_name": "rust-v0.168.0-fork.aaaaaaaa", "draft": False, "prerelease": False,
        }))

    def test_version_stamp_preserves_registry_packages_and_lock_references(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            crate = root / "codex-rs/cli"
            crate.mkdir(parents=True)
            (crate / "Cargo.toml").write_text('[package]\nname = "codex-cli"\nversion.workspace = true\n')
            implicit = root / "codex-rs/implicit"
            implicit.mkdir()
            (implicit / "Cargo.toml").write_text('[package]\nname = "codex-implicit"\nversion.workspace = true\n')
            (root / "codex-rs/Cargo.toml").write_text(
                '[workspace]\nmembers = ["cli"]\n[workspace.package]\nversion = "0.167.0"\n'
            )
            lock = root / "codex-rs/Cargo.lock"
            lock.write_text('version = 4\n[[package]]\nname = "codex-cli"\nversion = "0.0.0"\ndependencies = ["codex-implicit 0.0.0"]\n[[package]]\nname = "codex-implicit"\nversion = "0.0.0"\n[[package]]\nname = "codex-cli"\nversion = "0.167.0"\nsource = "registry+example"\n')
            release.set_workspace_version(root, "0.167.0", "0.167.0-fork.bbbbbbbb")
            self.assertIn('dependencies = ["codex-implicit 0.167.0-fork.bbbbbbbb"]', lock.read_text())
            self.assertIn('name = "codex-implicit"\nversion = "0.167.0-fork.bbbbbbbb"', lock.read_text())
            self.assertIn('version = "0.167.0"\nsource = "registry+example"', lock.read_text())
            self.assertIn('version = "0.167.0-fork.bbbbbbbb"', (root / "codex-rs/Cargo.toml").read_text())

    def test_archive_extraction_rejects_traversal_and_links(self):
        for name, kind in [("../outside", tarfile.REGTYPE), ("/absolute", tarfile.REGTYPE), ("bin/codex", tarfile.SYMTYPE)]:
            with self.subTest(name=name, kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive = root / "package.tar.gz"
                with tarfile.open(archive, "w:gz") as output:
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    if kind == tarfile.SYMTYPE:
                        member.linkname = "/outside"
                    output.addfile(member)
                with self.assertRaises(ValueError):
                    release.extract_package(archive, root / "package")

    def make_package(self, root, target=release.TARGETS[0]):
        package = root / "package"
        resource_target = release.upstream_target(target)
        commit = "a" * 40
        metadata = {
            "layoutVersion": 1, "version": "0.167.0", "target": resource_target,
            "variant": "codex", "entrypoint": "bin/codex", "execServer": "bin/codex-exec-server",
            "resourcesDir": "codex-resources", "pathDir": "codex-path",
        }
        files = {
            "bin/codex": b"upstream codex", "bin/codex-code-mode-host": b"signed host",
            "bin/codex-exec-server": b"signed executor", "codex-path/rg": b"ripgrep",
            "codex-resources/bwrap": b"upstream bwrap",
            "codex-resources/voice/bin/codex-voice-host": b"signed voice helper",
            "codex-resources/voice/lib/gstreamer.so": b"native runtime",
            "codex-resources/voice/runtime.json": json.dumps({"sourceCommit": commit}).encode(),
        }
        for name, contents in files.items():
            path = package / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        voice = {
            "schemaVersion": 1, "buildCommit": commit, "appVersion": "0.167.0",
            "appTarget": resource_target, "voiceTarget": target,
            "sha256": {name: release.digest(package / name) for name in files if name == "bin/codex" or "/voice/" in name},
        }
        release.write_json(package / "codex-package.json", metadata)
        release.write_json(package / "codex-resources/voice/manifest.json", voice)
        release.write_json(package / "fork-build.json", {
            "version": "0.167.0-fork.bbbbbbbb", "upstreamTag": "rust-v0.167.0",
            "upstreamCommit": commit, "forkCommit": "b" * 40, "target": target,
            "upstreamTarget": resource_target,
            "upstreamFiles": {path.relative_to(package).as_posix(): release.digest(path) for path in package.rglob("*") if path.is_file()},
        })
        return package, files

    def test_prepare_downloads_verified_musl_resources_for_each_gnu_target(self):
        for target in release.TARGETS[:2]:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                fixture, _ = self.make_package(root, target)
                source = root / "fixture.tar.gz"
                with tarfile.open(source, "w:gz") as archive:
                    for path in fixture.iterdir():
                        if path.name != "fork-build.json":
                            archive.add(path, arcname=path.name)

                def download(*args):
                    if args[0] == "git":
                        return "b" * 40
                    self.assertEqual(args[:3], ("gh", "release", "download"))
                    name = f"codex-package-{release.upstream_target(target)}.tar.gz"
                    self.assertIn(name, args)
                    directory = Path(args[-1])
                    shutil.copyfile(source, directory / name)
                    (directory / "codex-package_SHA256SUMS").write_text(
                        f"{release.digest(source)}  {name}\n"
                    )
                    return ""

                destination = root / "prepared"
                with patch("fork_release.run", side_effect=download), patch("fork_release.set_workspace_version"):
                    release.prepare(argparse.Namespace(
                        tag="rust-v0.167.0-fork.bbbbbbbb", upstream_commit="a" * 40,
                        target=target, package_dir=destination, env_file=root / "env",
                    ))
                provenance = json.loads((destination / "fork-build.json").read_text())
                self.assertEqual(provenance["target"], target)
                self.assertEqual(provenance["upstreamTarget"], release.upstream_target(target))
                self.assertIn("CODEX_BWRAP_SHA256=", (root / "env").read_text())

    def test_overlay_preserves_helpers_and_records_both_build_identities(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package, files = self.make_package(root)
            binary = root / "codex"
            binary.write_bytes(b"fork codex")
            archive = release.assemble(package, binary, root / "dist")
            extracted = root / "extracted"
            release.extract_package(archive, extracted)
            for name, original in files.items():
                if name != "bin/codex":
                    self.assertEqual((extracted / name).read_bytes(), original)
            self.assertEqual((extracted / "bin/codex").read_bytes(), b"fork codex")
            metadata = json.loads((extracted / "codex-package.json").read_text())
            self.assertEqual(metadata["version"], "0.167.0-fork.bbbbbbbb")
            self.assertEqual(metadata["target"], "x86_64-unknown-linux-gnu")
            self.assertEqual(metadata["upstreamTarget"], "x86_64-unknown-linux-musl")
            self.assertEqual(metadata["minimumGlibc"], "2.38")
            self.assertEqual(archive.name, "codex-package-x86_64-unknown-linux-gnu.tar.gz")
            voice = json.loads((extracted / "codex-resources/voice/manifest.json").read_text())
            self.assertEqual(voice["buildCommit"], "a" * 40)
            self.assertEqual(voice["appBuildCommit"], "b" * 40)
            self.assertEqual(voice["appTarget"], "x86_64-unknown-linux-gnu")
            self.assertEqual(voice["voiceTarget"], "x86_64-unknown-linux-gnu")
            self.assertEqual(voice["sha256"]["bin/codex"], release.digest(binary))

    def test_overlay_rejects_corrupted_upstream_resources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package, _ = self.make_package(root)
            (package / "codex-resources/voice/lib/gstreamer.so").write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                release.assemble(package, root / "unused", root / "dist")

    def test_upstream_archive_checksum_is_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "package.tar.gz"
            archive.write_bytes(b"contents")
            manifest = root / "SHA256SUMS"
            manifest.write_text(f"{release.digest(archive)}  {archive.name}\n")
            release.verify_archive(archive, manifest)
            archive.write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                release.verify_archive(archive, manifest)

    def test_first_release_handles_only_not_found_as_an_empty_channel(self):
        import subprocess
        missing = subprocess.CompletedProcess([], 1, "", "gh: Not Found (HTTP 404)")
        denied = subprocess.CompletedProcess([], 1, "", "gh: Forbidden (HTTP 403)")
        with patch("fork_release.subprocess.run", return_value=missing):
            self.assertIsNone(release.github_json("repos/example/releases/latest", missing_ok=True))
        with patch("fork_release.subprocess.run", return_value=denied), self.assertRaises(RuntimeError):
            release.github_json("repos/example/releases/latest", missing_ok=True)

    def test_publication_requires_all_platforms_and_keeps_releases_immutable(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with self.assertRaisesRegex(ValueError, "six platform"):
                release.publish("rust-v0.167.0-fork.bbbbbbbb", directory)
            for target in release.TARGETS:
                (directory / f"codex-package-{target}.tar.gz").write_bytes(b"fixture archive")
            with patch.dict("os.environ", {"GITHUB_REPOSITORY": "ayanamist/codex"}), patch(
                "fork_release.github_json", return_value={"draft": False}
            ), patch("fork_release.run", return_value="b" * 40), self.assertRaisesRegex(ValueError, "already published"):
                release.publish("rust-v0.167.0-fork.bbbbbbbb", directory)

    def test_first_publication_is_stable_and_latest_after_all_assets_upload(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for target in release.TARGETS:
                (directory / f"codex-package-{target}.tar.gz").write_bytes(b"fixture archive")
            with patch.dict("os.environ", {"GITHUB_REPOSITORY": "ayanamist/codex"}), patch(
                "fork_release.github_json", return_value=None
            ), patch("fork_release.run", return_value="b" * 40) as run:
                release.publish("rust-v0.167.0-fork.bbbbbbbb", directory)
            commands = [call.args for call in run.call_args_list]
            publication = [args for args in commands if args[:2] == ("gh", "release")]
            self.assertEqual([args[2] for args in publication], ["create", "upload", "edit"])
            self.assertIn("--draft", publication[0])
            self.assertIn("--prerelease=false", publication[-1])
            self.assertIn("--latest=true", publication[-1])
            self.assertEqual(len((directory / "codex-package_SHA256SUMS").read_text().splitlines()), 6)

    def test_latest_promotion_uses_ancestry_instead_of_suffix_order(self):
        for status, expected in [("ahead", True), ("identical", True), ("behind", False), ("diverged", False)]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                for target in release.TARGETS:
                    (directory / f"codex-package-{target}.tar.gz").write_bytes(b"fixture archive")
                latest = {"tag_name": "rust-v0.167.0-fork.bbbbbbbb", "draft": False, "prerelease": False}
                with patch.dict("os.environ", {"GITHUB_REPOSITORY": "ayanamist/codex"}), patch(
                    "fork_release.github_json", side_effect=[None, latest, {"status": status}]
                ) as api, patch("fork_release.run", return_value="a" * 40) as run:
                    release.publish("rust-v0.167.0-fork.aaaaaaaa", directory)
                self.assertEqual(api.call_args.args[0], "repos/ayanamist/codex/compare/rust-v0.167.0-fork.bbbbbbbb..." + "a" * 40)
                self.assertIn(f"--latest={str(expected).lower()}", run.call_args.args)

    def test_latest_promotion_from_numbered_release_and_custom_suffix(self):
        for previous in ["0.167.0-ayanamist.2", "0.167.0-custom-build.ABC123"]:
            with self.subTest(previous=previous), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                for target in release.TARGETS:
                    (directory / f"codex-package-{target}.tar.gz").write_bytes(b"fixture archive")
                latest = {"tag_name": "rust-v" + previous, "draft": False, "prerelease": False}
                with patch.dict("os.environ", {"GITHUB_REPOSITORY": "ayanamist/codex"}), patch(
                    "fork_release.github_json", side_effect=[None, latest, {"status": "ahead"}]
                ), patch("fork_release.run", return_value="a" * 40) as run:
                    release.publish("rust-v0.167.0-fork.aaaaaaaa", directory)
                self.assertIn("--latest=true", run.call_args.args)

    def test_github_release_metadata_determines_the_stable_channel(self):
        self.assertTrue(should_make_latest("0.167.0-custom-build.ABC123", {
            "tag_name": "rust-v0.167.0-alpha.1", "draft": False, "prerelease": False,
        }))
        with self.assertRaises(ValueError):
            should_make_latest("0.167.0-fork.aaaaaaaa", {
                "tag_name": "rust-v0.167.0-custom-build.ABC123", "draft": False, "prerelease": True,
            })


if __name__ == "__main__":
    unittest.main()
