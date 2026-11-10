from pathlib import Path
import subprocess
import tempfile
import unittest

from check_linux_glibc import check_package, required_glibc_versions


class GlibcCompatibilityTests(unittest.TestCase):
    def test_reads_only_required_versions_and_handles_relr(self):
        output = """Version definition section '.gnu.version_d' contains 1 entry:
  Name: GLIBC_2.99
Version needs section '.gnu.version_r' contains 2 entries:
  Name: GLIBC_2.9
  Name: GLIBC_2.38
  Name: GLIBC_ABI_DT_RELR
"""
        self.assertEqual(required_glibc_versions(output), {(2, 9), (2, 38), (2, 36)})

    def test_rejects_private_or_unknown_glibc_abi_requirements(self):
        for name in ("GLIBC_PRIVATE", "GLIBC_ABI_UNKNOWN"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "unsupported glibc import"):
                required_glibc_versions(
                    f"Version needs section '.gnu.version_r' contains 1 entry:\n  Name: {name}\n"
                )

    def test_checks_real_elf_imports_in_nested_libraries(self):
        # A tiny versioned dependency exercises real readelf output without
        # requiring a particular host glibc or an alternate runtime install.
        for version, accepted in (("2.9", True), ("2.38", True), ("2.39", False), ("2.100", False)):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                package = root / "package"
                libraries = package / "codex-resources/voice/lib"
                libraries.mkdir(parents=True)
                provider = root / "provider.c"
                provider.write_text("int sample(void) { return 1; }\n")
                versions = root / "versions.map"
                versions.write_text(f"GLIBC_{version} {{ global: sample; }};\n")
                dependency = libraries / "libfixture.so"
                subprocess.run([
                    "cc", "-shared", "-fPIC", str(provider),
                    f"-Wl,--version-script={versions}", "-o", str(dependency),
                ], check=True, capture_output=True)
                # Exporting a new GLIBC version by itself must not fail.
                self.assertEqual(check_package(package), 1)
                consumer = root / "consumer.c"
                consumer.write_text("extern int sample(void); int use_sample(void) { return sample(); }\n")
                subprocess.run([
                    "cc", "-shared", "-fPIC", str(consumer), f"-L{libraries}",
                    "-lfixture", "-o", str(libraries / "libconsumer.so"),
                ], check=True, capture_output=True)
                if accepted:
                    self.assertEqual(check_package(package), 2)
                else:
                    with self.assertRaisesRegex(ValueError, f"libconsumer.so: requires glibc {version}"):
                        check_package(package)

    def test_rejects_an_empty_or_non_elf_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            (package / "manifest.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "no ELF"):
                check_package(package)


if __name__ == "__main__":
    unittest.main()
