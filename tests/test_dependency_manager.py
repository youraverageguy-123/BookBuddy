import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dependency_manager


class DependencyManagerTests(unittest.TestCase):
    def _requirements_file(self, contents: str) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "requirements.txt"
        path.write_text(contents, encoding="utf-8")
        return path

    def test_requirements_include_direct_runtime_dependencies(self):
        names = {item.name.lower() for item in dependency_manager.read_requirements()}
        self.assertIn("python-multipart", names)
        self.assertTrue({"numpy", "pillow", "paddleocr"}.isdisjoint(names))
        self.assertNotIn("google-genai", names)
        gemini_names = {
            item.name.lower()
            for item in dependency_manager.read_requirements(dependency_manager.GEMINI_REQUIREMENTS_PATH)
        }
        self.assertEqual({"google-genai"}, gemini_names)
        image_names = {
            item.name.lower()
            for item in dependency_manager.read_requirements(dependency_manager.IMAGE_REQUIREMENTS_PATH)
        }
        self.assertTrue(
            {"numpy", "pillow", "opencv-python-headless", "imagehash", "paddleocr", "paddlepaddle"}.issubset(image_names)
        )
        dictionary_names = {
            item.name.lower()
            for item in dependency_manager.read_requirements(dependency_manager.DICTIONARY_REQUIREMENTS_PATH)
        }
        self.assertTrue({"spacy", "wn", "cmudict"}.issubset(dictionary_names))

    def test_missing_requirements_reports_absent_and_outdated_packages(self):
        requirements_path = self._requirements_file("available>=2.0\nmissing>=1.0\n")

        def installed_version(package_name):
            if package_name == "available":
                return "1.0"
            raise dependency_manager.metadata.PackageNotFoundError(package_name)

        with mock.patch("dependency_manager.metadata.version", side_effect=installed_version):
            missing = dependency_manager.missing_requirements(requirements_path)

        self.assertEqual(["available>=2.0", "missing>=1.0"], [item.display for item in missing])

    def test_version_comparison_is_standard_library_and_conservative(self):
        self.assertTrue(dependency_manager._version_satisfies("2.1.0", dependency_manager.RequirementSpec("x", ">=", "2.0")))
        self.assertFalse(dependency_manager._version_satisfies("1.9", dependency_manager.RequirementSpec("x", ">=", "2.0")))
        self.assertFalse(dependency_manager._version_satisfies("2.0rc1", dependency_manager.RequirementSpec("x", ">=", "2.0")))
        with self.assertRaisesRegex(ValueError, "Unsupported numeric requirement version"):
            dependency_manager._version_satisfies("2.0", dependency_manager.RequirementSpec("x", ">=", "latest"))

    def test_approved_install_uses_the_current_python_and_rechecks(self):
        requirements_path = self._requirements_file("example>=1.0\n")
        requirement = dependency_manager.RequirementSpec("example", ">=", "1.0")

        with mock.patch("dependency_manager.missing_requirements", side_effect=[[requirement], []]), mock.patch(
            "builtins.input", return_value="yes"
        ), mock.patch("dependency_manager.subprocess.run", return_value=mock.Mock(returncode=0)) as run, mock.patch.object(
            dependency_manager.sys.stdin, "isatty", return_value=True
        ):
            dependency_manager.ensure_dependencies("test", requirements_path)

        command = run.call_args.args[0]
        self.assertEqual(dependency_manager.sys.executable, command[0])
        self.assertEqual(["-m", "pip", "install", "-r"], command[1:5])
        self.assertEqual(str(requirements_path.resolve()), command[5])

    def test_declined_install_explains_that_startup_stops(self):
        requirements_path = self._requirements_file("example>=1.0\n")
        requirement = dependency_manager.RequirementSpec("example", ">=", "1.0")

        with mock.patch("dependency_manager.missing_requirements", return_value=[requirement]), mock.patch(
            "builtins.input", return_value="n"
        ), mock.patch.object(dependency_manager.sys.stdin, "isatty", return_value=True), self.assertRaises(
            dependency_manager.DependencyInstallationRequired
        ):
            dependency_manager.ensure_dependencies("test", requirements_path)


if __name__ == "__main__":
    unittest.main()
