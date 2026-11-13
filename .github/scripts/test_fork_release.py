import argparse
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import fork_release as release
from releases import is_valid_stable_release_version, should_make_latest, should_update_version


class ForkReleaseTests(unittest.TestCase):
    def reference(self, commit, kind="commit"):
        return {"object": {"type": kind, "sha": commit}}

    def test_build_cache_settings_ignore_release_identity_and_dependency_updates(self):
        manifest = {
            "workspace": {
                "package": {"version": "0.167.0", "edition": "2024"},
                "resolver": "2",
                "dependencies": {"serde": "1"},
            },
            "profile": {"release": {"lto": "thin", "codegen-units": 4}},
            "patch": {"crates-io": {"v8": {"git": "https://example.com/v8", "rev": "a" * 40}}},
        }
        before = release.build_cache_settings_hash(manifest)
        manifest["workspace"]["package"]["version"] = "0.167.1-fork.bbbbbbbb"
        manifest["workspace"]["dependencies"]["serde"] = "2"
        self.assertEqual(release.build_cache_settings_hash(manifest), before)

        for section, field, value in [
            ("profile", "release", {"lto": "off", "codegen-units": 4}),
            ("patch", "crates-io", {"v8": {"git": "https://example.com/v8", "rev": "c" * 40}}),
            ("workspace", "resolver", "3"),
            ("workspace", "package", {"version": "0.167.1", "edition": "2027"}),
        ]:
            with self.subTest(section=section, field=field):
                changed = copy.deepcopy(manifest)
                changed[section][field] = value
                self.assertNotEqual(release.build_cache_settings_hash(changed), before)

        reordered = dict(reversed(list(manifest.items())))
        self.assertEqual(release.build_cache_settings_hash(reordered), before)

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

    def test_retry_reuses_the_same_commit_tag_even_when_published(self):
        commit = "b" * 40
        with patch.dict("os.environ", {"GITHUB_REPOSITORY": "ayanamist/codex"}), patch(
            "fork_release.github_json", side_effect=[{"object": {"sha": commit}}, self.reference(commit)]
        ) as api:
            self.assertEqual(release.automatic_tag("0.167.0", commit), ("rust-v0.167.0-fork.bbbbbbbb", True))
            self.assertFalse(any(call.kwargs.get("data") for call in api.call_args_list))

    def test_concurrent_platform_workflows_accept_a_tag_reserved_by_a_sibling(self):
        commit = "b" * 40
        for sibling, accepted in [(self.reference(commit), True), (self.reference("c" * 40), False), (None, False)]:
            with self.subTest(sibling=sibling), patch.dict("os.environ", {"GITHUB_REPOSITORY": "ayanamist/codex"}), patch(
                "fork_release.github_json",
                side_effect=[{"object": {"sha": commit}}, None, RuntimeError("Reference already exists"), sibling],
            ):
                if accepted:
                    self.assertEqual(release.automatic_tag("0.167.0", commit), ("rust-v0.167.0-fork.bbbbbbbb", True))
                else:
                    with self.assertRaises(RuntimeError):
                        release.automatic_tag("0.167.0", commit)

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
        changed.assert_called_once_with(commit, head, ignored_paths=())
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
            sibling = ".github/workflows/rust-release-linux.yml"
            (root / sibling).parent.mkdir(parents=True)
            (root / sibling).write_text("name: sibling\n")
            workflow = commit()
            self.assertFalse(release.only_documentation_changed(code, workflow, cwd=root))
            self.assertTrue(release.only_documentation_changed(code, workflow, ignored_paths=(sibling,), cwd=root))

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
            root = Path(temporary)
            output = root / "outputs"
            (root / "codex-rs").mkdir()
            (root / "codex-rs/Cargo.toml").write_text('[workspace.package]\nversion = "0.167.0"\n')
            (root / "codex-rs/rust-toolchain.toml").write_text('[toolchain]\nchannel = "1.95.0"\n')
            with patch("fork_release.ROOT", root), patch("fork_release.github_json", return_value={"tag_name": "rust-v0.167.0", "draft": False, "prerelease": False}), patch(
                "fork_release.run", side_effect=["", upstream, "", commit]
            ), patch("fork_release.automatic_tag", return_value=("rust-v0.167.0-fork.bbbbbbbb", True)):
                release.resolve(None, output)
            values = dict(line.split("=", 1) for line in output.read_text().splitlines())
            self.assertEqual(values["tag"], "rust-v0.167.0-fork.bbbbbbbb")
            self.assertEqual(values["fork_commit"], commit)
            self.assertEqual(values["upstream_commit"], upstream)
            self.assertEqual(values["should_publish"], "true")
            self.assertEqual(values["should_build"], "true")

    def test_resolve_requires_a_stable_upstream_base_before_build_normalization(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "codex-rs").mkdir()
            manifest = root / "codex-rs/Cargo.toml"
            for base in ["0.0.0", "0.167.0-alpha.1", "0.167.0+build", "invalid"]:
                with self.subTest(base=base), patch("fork_release.ROOT", root), patch("fork_release.github_json") as api:
                    manifest.write_text(f'[workspace.package]\nversion = "{base}"\n')
                    with self.assertRaisesRegex(ValueError, "upstream release checkout"):
                        release.resolve(None, root / "output")
                    api.assert_not_called()
            manifest.write_text('[workspace.package]\nversion = "0.167.0"\n')
            with patch("fork_release.ROOT", root), self.assertRaisesRegex(ValueError, "unchanged upstream"):
                release.resolve("rust-v0.168.0-fork.bbbbbbbb", root / "output")

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

    def make_package(self, root, target=release.TARGETS[0], *, executor_inventory=True):
        package = root / "package"
        resource_target = release.upstream_target(target)
        suffix = ".exe" if "windows" in target else ""
        commit = "a" * 40
        metadata = {
            "layoutVersion": 1, "version": "0.167.0", "target": resource_target,
            "variant": "codex", "entrypoint": f"bin/codex{suffix}", "execServer": f"bin/codex-exec-server{suffix}",
            "resourcesDir": "codex-resources", "pathDir": "codex-path",
        }
        files = {
            f"bin/codex{suffix}": b"upstream codex", f"bin/codex-code-mode-host{suffix}": b"signed host",
            f"bin/codex-exec-server{suffix}": b"signed executor", f"codex-path/rg{suffix}": b"ripgrep",
            "codex-resources/bwrap": b"upstream bwrap",
            f"codex-resources/voice/bin/codex-voice-host{suffix}": b"signed voice helper",
            "codex-resources/voice/lib/gstreamer.so": b"native runtime",
            "codex-resources/voice/runtime.json": json.dumps({"sourceCommit": commit}).encode(),
        }
        if suffix:
            for name in ["codex-command-runner", "codex-windows-sandbox-setup"]:
                files[f"codex-resources/{name}{suffix}"] = b"signed sandbox helper"
        for name, contents in files.items():
            path = package / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        voice = {
            "schemaVersion": 1, "buildCommit": commit, "appVersion": "0.167.0",
            "appTarget": resource_target, "voiceTarget": target,
            "sha256": {name: release.digest(package / name) for name in files if name == metadata["entrypoint"] or (executor_inventory and name == metadata["execServer"]) or "/voice/" in name},
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
        for target in (target for target in release.TARGETS if target.endswith("-linux-gnu")):
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

                workspace = root / "codex-rs"
                workspace.mkdir()
                (workspace / "Cargo.toml").write_text('[workspace.package]\nversion = "0.0.0"\n')
                (workspace / "Cargo.lock").write_text('version = 4\n[[package]]\nname = "codex-cli"\nversion = "0.0.0"\n')
                before = {path.name: path.read_bytes() for path in workspace.iterdir()}
                destination = root / "prepared"
                with patch("fork_release.run", side_effect=download), patch("fork_release.ROOT", root):
                    release.prepare(argparse.Namespace(
                        tag="rust-v0.167.0-fork.bbbbbbbb", upstream_commit="a" * 40,
                        target=target, package_dir=destination, env_file=root / "env",
                    ))
                provenance = json.loads((destination / "fork-build.json").read_text())
                self.assertEqual(provenance["target"], target)
                self.assertEqual(provenance["upstreamTarget"], release.upstream_target(target))
                self.assertIn("CODEX_BWRAP_SHA256=", (root / "env").read_text())
                self.assertIn("CODEX_RELEASE_VERSION=0.167.0-fork.bbbbbbbb\n", (root / "env").read_text())
                self.assertEqual({path.name: path.read_bytes() for path in workspace.iterdir()}, before)

    def test_overlay_rebuilds_cli_and_executor_and_preserves_other_helpers(self):
        for target in release.TARGETS:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package, files = self.make_package(root, target)
                binary, executor = root / "codex", root / "executor"
                binary.write_bytes(b"fork codex")
                executor.write_bytes(b"fork executor")
                suffix = ".exe" if "windows" in target else ""
                rebuilt = {f"bin/codex{suffix}": binary, f"bin/codex-exec-server{suffix}": executor}
                archive = release.assemble(package, binary, executor, root / "dist")
                extracted = root / "extracted"
                release.extract_package(archive, extracted)
                for name, original in files.items():
                    self.assertEqual((extracted / name).read_bytes(), rebuilt[name].read_bytes() if name in rebuilt else original)
                metadata = json.loads((extracted / "codex-package.json").read_text())
                self.assertEqual(metadata["version"], "0.167.0-fork.bbbbbbbb")
                self.assertEqual(metadata["target"], target)
                self.assertEqual(metadata["upstreamTarget"], release.upstream_target(target))
                if "linux" in target:
                    self.assertEqual(metadata["minimumGlibc"], "2.38")
                self.assertEqual(archive.name, f"codex-package-{target}.tar.gz")
                voice = json.loads((extracted / "codex-resources/voice/manifest.json").read_text())
                self.assertEqual(voice["buildCommit"], "a" * 40)
                self.assertEqual(voice["appBuildCommit"], "b" * 40)
                self.assertEqual(voice["appTarget"], target)
                self.assertEqual(voice["voiceTarget"], target)
                provenance = json.loads((extracted / "fork-build.json").read_text())
                self.assertEqual(provenance["entrypointSha256"], release.digest(binary))
                self.assertEqual(provenance["execServerSha256"], release.digest(executor))
                self.assertEqual(set(provenance["rebuiltBinaries"]), set(rebuilt))
                for name, source in rebuilt.items():
                    self.assertEqual(voice["sha256"][name], release.digest(source))
                    self.assertEqual(provenance["rebuiltBinaries"][name], {"sha256": release.digest(source), "buildCommit": "b" * 40})
                    self.assertNotIn(name, provenance["upstreamFiles"])
                for name in set(files) - set(rebuilt):
                    self.assertEqual(provenance["upstreamFiles"][name], release.digest(extracted / name))

    def test_overlay_requires_a_fork_executor_before_replacing_any_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package, files = self.make_package(root)
            binary = root / "codex"
            binary.write_bytes(b"fork codex")
            with self.assertRaisesRegex(ValueError, "Missing or unsafe fork binary"):
                release.assemble(package, binary, root / "missing-executor", root / "dist")
            for name, original in files.items():
                self.assertEqual((package / name).read_bytes(), original)

    def test_overlay_accepts_inventory_without_optional_executor_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package, _ = self.make_package(root, executor_inventory=False)
            binary, executor = root / "codex", root / "executor"
            binary.write_bytes(b"fork codex")
            executor.write_bytes(b"fork executor")
            archive = release.assemble(package, binary, executor, root / "dist")
            extracted = root / "extracted"
            release.extract_package(archive, extracted)
            voice = json.loads((extracted / "codex-resources/voice/manifest.json").read_text())
            self.assertNotIn("bin/codex-exec-server", voice["sha256"])
            self.assertEqual((extracted / "bin/codex-exec-server").read_bytes(), executor.read_bytes())

    def test_assemble_command_requires_executor_input(self):
        result = subprocess.run([
            sys.executable, str(Path(release.__file__)), "assemble",
            "--package-dir", "unused", "--binary", "unused", "--output-dir", "unused",
        ], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--exec-server-binary", result.stderr)

    def test_overlay_rejects_corrupted_upstream_resources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package, _ = self.make_package(root)
            (package / "codex-resources/voice/lib/gstreamer.so").write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                release.assemble(package, root / "unused", root / "unused-executor", root / "dist")

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

    def make_archives(self, directory, targets=None):
        for target in targets or release.TARGETS:
            (directory / f"codex-package-{target}.tar.gz").write_bytes(b"fixture archive")

    def assets(self, *targets):
        return {"assets": [
            {"name": f"codex-package-{target}.tar.gz", "digest": "sha256:" + "d" * 64} for target in targets
        ]}

    def test_publication_requires_a_platform_package(self):
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(ValueError, "No platform package"):
            release.publish("rust-v0.167.0-fork.bbbbbbbb", Path(temporary))

    def publish(self, tag, directory, responses):
        with patch.dict("os.environ", {"GITHUB_REPOSITORY": "ayanamist/codex"}), patch(
            "fork_release.github_json", side_effect=responses
        ) as api, patch("fork_release.run", return_value="b" * 40) as run:
            release.publish(tag, directory)
        return api, [call.args for call in run.call_args_list if call.args[:2] == ("gh", "release")]

    def test_first_platform_creates_a_non_latest_release_and_later_ones_only_add_files(self):
        linux, mac = release.TARGETS[0], release.TARGETS[1]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.make_archives(directory, [mac])
            _, publication = self.publish("rust-v0.167.0-fork.bbbbbbbb", directory, [None, self.assets(mac), self.assets(mac)])
            self.assertEqual([args[2] for args in publication], ["create", "upload", "upload"])
            self.assertNotIn("--draft", publication[0])
            self.assertIn("--prerelease", publication[0])
            self.assertIn("--latest=false", publication[0])
            self.assertNotIn("config-schema.json", " ".join(publication[1]))
            self.assertEqual((directory / "codex-package_SHA256SUMS").read_text().splitlines(), [
                f"{release.digest(directory / f'codex-package-{mac}.tar.gz')}  codex-package-{mac}.tar.gz",
            ])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.make_archives(directory, [linux])
            _, publication = self.publish(
                "rust-v0.167.0-fork.bbbbbbbb", directory, [{"draft": False}, self.assets(mac, linux), self.assets(mac, linux)],
            )
            self.assertEqual([args[2] for args in publication], ["upload", "upload"])
            names = [line.split()[1] for line in (directory / "codex-package_SHA256SUMS").read_text().splitlines()]
            self.assertEqual(names, [f"codex-package-{linux}.tar.gz", f"codex-package-{mac}.tar.gz"])

    def test_checksums_are_rewritten_when_a_sibling_uploads_concurrently(self):
        linux, mac = release.TARGETS[0], release.TARGETS[1]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.make_archives(directory, [linux])
            _, publication = self.publish(
                "rust-v0.167.0-fork.bbbbbbbb", directory,
                [{"draft": False}, self.assets(linux), self.assets(linux, mac), self.assets(linux, mac)],
            )
            self.assertEqual([args[2] for args in publication].count("upload"), 3)
            self.assertEqual(len((directory / "codex-package_SHA256SUMS").read_text().splitlines()), 2)

    def test_draft_release_from_an_earlier_run_is_published_as_a_prerelease(self):
        linux = release.TARGETS[0]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.make_archives(directory, [linux])
            _, publication = self.publish(
                "rust-v0.167.0-fork.bbbbbbbb", directory, [{"draft": True}, self.assets(linux), self.assets(linux)],
            )
            self.assertEqual(publication[0][2], "edit")
            self.assertIn("--draft=false", publication[0])
            self.assertIn("--prerelease=true", publication[0])
            self.assertIn("--latest=false", publication[0])

    def test_a_complete_release_is_never_promoted_to_latest_automatically(self):
        every = self.assets(*release.TARGETS)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.make_archives(directory, [release.TARGETS[0]])
            _, publication = self.publish("rust-v0.167.0-fork.bbbbbbbb", directory, [{"draft": False}, every, every])
            self.assertEqual([args for args in publication if args[2] == "edit"], [])

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
