"""Behavior of the short installer frontend; release validation stays in its delegate."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET


SCRIPT = Path(__file__).resolve().parents[1] / "install-local.py"


class InstallLocalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("install_local", SCRIPT)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def invoke(self, args):
        output, errors = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = self.module.run(args)
        return code, output.getvalue(), errors.getvalue()

    def test_success_installs_then_renders_real_absolute_uri(self):
        with tempfile.TemporaryDirectory() as raw:
            destination = Path(raw) / "한글 space & quote' repo"
            delegated = []

            def install(path):
                delegated.append(path)
                path.mkdir()

            with patch.object(self.module.INSTALLER, "install_public_release", install):
                code, output, errors = self.invoke(["--repository", str(destination)])
            self.assertEqual(0, code, errors)
            self.assertEqual([destination.absolute()], delegated)
            self.assertIn(destination.resolve().as_uri(), output)
            self.assertIn('testImplementation("io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.2")', output)
            self.assertIn("ignoreGradleMetadataRedirection()", output)

    def test_installer_rejection_never_prints_build_configuration(self):
        with patch.object(self.module.INSTALLER, "install_public_release",
                          side_effect=self.module.INSTALLER.PublicInstallError("rejected release")):
            code, output, errors = self.invoke([])
        self.assertEqual(2, code)
        self.assertNotIn("testImplementation", output)
        self.assertIn("rejected release", errors)

    def test_relative_target_uses_callers_directory(self):
        with tempfile.TemporaryDirectory() as raw:
            previous = Path.cwd()
            try:
                os.chdir(raw)
                destination = Path.cwd() / "new-repo"
                with patch.object(self.module.INSTALLER, "install_public_release",
                                  side_effect=lambda path: path.mkdir()) as install:
                    code, output, errors = self.invoke(["--repository", "new-repo"])
                self.assertEqual(0, code, errors)
                install.assert_called_once_with(destination)
                self.assertIn(destination.as_uri(), output)
            finally:
                os.chdir(previous)

    def test_dangling_symlink_is_not_replaced_or_followed(self):
        with tempfile.TemporaryDirectory() as raw:
            destination = Path(raw) / "repo-link"
            missing = Path(raw) / "missing"
            destination.symlink_to(missing, target_is_directory=True)
            with patch.object(self.module.INSTALLER, "_download_with_curl") as download:
                code, output, _ = self.invoke(["--repository", str(destination)])
            self.assertEqual(2, code)
            self.assertNotIn("testImplementation", output)
            self.assertTrue(destination.is_symlink())
            self.assertFalse(missing.exists())
            download.assert_not_called()

    def test_existing_destination_preserved_by_real_delegate_before_download(self):
        with tempfile.TemporaryDirectory() as raw:
            destination = Path(raw)
            sentinel = destination / "keep.txt"
            sentinel.write_text("unchanged", encoding="utf-8")
            with patch.object(self.module.INSTALLER, "_download_with_curl") as download:
                code, output, _ = self.invoke(["--repository", str(destination)])
            self.assertEqual(2, code)
            self.assertNotIn("testImplementation", output)
            self.assertEqual("unchanged", sentinel.read_text(encoding="utf-8"))
            download.assert_not_called()

    def test_missing_parent_does_not_create_directories(self):
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw) / "not-created"
            code, _, _ = self.invoke(["--repository", str(parent / "repo")])
            self.assertEqual(2, code)
            self.assertFalse(parent.exists())

    def test_maven_output_is_xml_and_test_scoped(self):
        with tempfile.TemporaryDirectory() as raw:
            destination = Path(raw) / "repo & 한글"
            with patch.object(self.module.INSTALLER, "install_public_release", lambda p: p.mkdir()):
                code, output, errors = self.invoke(["--repository", str(destination), "--format", "maven"])
            self.assertEqual(0, code, errors)
            fragment = output[output.index("\n<repositories>\n") + 1:].strip()
            root = ET.fromstring("<project>" + fragment + "</project>")
            self.assertEqual(destination.resolve().as_uri(), root.findtext("repositories/repository/url"))
            self.assertEqual("test", root.findtext("dependencies/dependency/scope"))
            self.assertIsNone(root.find("dependencies/dependency/systemPath"))

    def test_invalid_format_does_not_install(self):
        with patch.object(self.module.INSTALLER, "install_public_release") as install:
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
                self.module.run(["--format", "unknown"])
            self.assertEqual(2, error.exception.code)
            install.assert_not_called()


if __name__ == "__main__":
    unittest.main()
