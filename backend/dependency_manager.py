"""Startup dependency checks for BookBuddy entry points.

The module deliberately uses only the Python standard library so it can run
before FastAPI, Gemini, or any image-processing package is imported.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
import re
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_ROOT = PROJECT_ROOT / "requirements"
DEFAULT_REQUIREMENTS_PATH = REQUIREMENTS_ROOT / "requirements.txt"
IMAGE_REQUIREMENTS_PATH = REQUIREMENTS_ROOT / "requirements-image.txt"
DICTIONARY_REQUIREMENTS_PATH = REQUIREMENTS_ROOT / "requirements-dictionary.txt"
GEMINI_REQUIREMENTS_PATH = REQUIREMENTS_ROOT / "requirements-ai-gemini.txt"
PDF_REQUIREMENTS_PATH = REQUIREMENTS_ROOT / "requirements-pdf.txt"
_REQUIREMENT_PATTERN = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)(?:\s*(==|>=|<=|>|<|~=)\s*([^\s;#]+))?"
)


class DependencyInstallationRequired(RuntimeError):
    """Raised when BookBuddy cannot start without its declared packages."""


@dataclass(frozen=True)
class RequirementSpec:
    name: str
    operator: str = ""
    version: str = ""

    @property
    def display(self) -> str:
        return f"{self.name}{self.operator}{self.version}" if self.operator else self.name


def read_requirements(requirements_path: Path | str = DEFAULT_REQUIREMENTS_PATH) -> list[RequirementSpec]:
    """Read simple pinned/minimum-version requirements from the project file."""
    path = Path(requirements_path)
    if not path.is_file():
        raise FileNotFoundError(f"requirements.txt was not found: {path}")

    requirements: list[RequirementSpec] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        match = _REQUIREMENT_PATTERN.fullmatch(line)
        if match is None:
            raise ValueError(f"Unsupported requirement declaration: {raw_line}")
        name, operator, version = match.groups()
        requirements.append(RequirementSpec(name, operator or "", version or ""))
    return requirements


def _version_satisfies(installed: str, requirement: RequirementSpec) -> bool:
    """Compare the numeric release versions supported by project manifests."""
    if not requirement.operator:
        return True

    def release_tuple(value: str) -> tuple[int, ...] | None:
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)*)\s*", str(value or ""))
        return tuple(int(part) for part in match.group(1).split(".")) if match else None

    current = release_tuple(installed)
    required = release_tuple(requirement.version)
    if required is None:
        raise ValueError(f"Unsupported numeric requirement version: {requirement.display}")
    if current is None:
        return False
    width = max(len(current), len(required))
    current = current + (0,) * (width - len(current))
    required_padded = required + (0,) * (width - len(required))
    comparisons = {
        "==": current == required_padded,
        ">=": current >= required_padded,
        "<=": current <= required_padded,
        ">": current > required_padded,
        "<": current < required_padded,
    }
    if requirement.operator in comparisons:
        return comparisons[requirement.operator]
    if requirement.operator == "~=":
        compatible_prefix = required[:-1] if len(required) > 2 else required[:1]
        return current >= required_padded and current[:len(compatible_prefix)] == compatible_prefix
    raise ValueError(f"Unsupported requirement operator: {requirement.operator}")


def missing_requirements(requirements_path: Path | str = DEFAULT_REQUIREMENTS_PATH) -> list[RequirementSpec]:
    missing: list[RequirementSpec] = []
    for requirement in read_requirements(requirements_path):
        try:
            installed_version = metadata.version(requirement.name)
        except metadata.PackageNotFoundError:
            missing.append(requirement)
            continue
        if not _version_satisfies(installed_version, requirement):
            missing.append(requirement)
    return missing


def install_command(requirements_path: Path | str = DEFAULT_REQUIREMENTS_PATH) -> list[str]:
    return [sys.executable, "-m", "pip", "install", "-r", str(Path(requirements_path).resolve())]


def _print_manual_install_instructions(requirements_path: Path | str) -> None:
    command = install_command(requirements_path)
    print("Install the missing dependencies with:")
    print("  " + subprocess.list2cmdline(command))


def ensure_dependencies(
    application_name: str,
    requirements_path: Path | str = DEFAULT_REQUIREMENTS_PATH,
    *,
    prompt: bool = True,
) -> None:
    """Stop startup cleanly or install only after explicit user approval."""
    missing = missing_requirements(requirements_path)
    if not missing:
        return

    print(f"\n{application_name} is missing required dependencies:")
    for requirement in missing:
        print(f"  - {requirement.display}")

    interactive = bool(getattr(sys.stdin, "isatty", lambda: False)())
    should_install = False
    if prompt and interactive:
        try:
            answer = input("Install the missing dependencies now? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        should_install = answer in {"y", "yes"}

    if not should_install:
        _print_manual_install_instructions(requirements_path)
        if not interactive:
            print("Automatic installation needs an interactive terminal.")
        raise DependencyInstallationRequired("Required dependencies are unavailable.")

    command = install_command(requirements_path)
    print("Installing dependencies from requirements.txt...")
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        _print_manual_install_instructions(requirements_path)
        raise DependencyInstallationRequired("Dependency installation failed.")

    still_missing = missing_requirements(requirements_path)
    if still_missing:
        print("Some dependencies are still unavailable after installation:")
        for requirement in still_missing:
            print(f"  - {requirement.display}")
        raise DependencyInstallationRequired("Dependency installation was incomplete.")

    print("All BookBuddy dependencies are installed.")


def _main() -> int:
    parser = argparse.ArgumentParser(description="Check or install BookBuddy dependencies.")
    parser.add_argument("--check", action="store_true", help="Report missing dependencies without prompting.")
    parser.add_argument("--install", action="store_true", help="Install requirements without prompting.")
    parser.add_argument(
        "--image",
        action="store_true",
        help="Check or install the optional local image pipeline requirements.",
    )
    parser.add_argument("--dictionary", action="store_true", help="Check or install optional dictionary requirements.")
    parser.add_argument("--ai-gemini", action="store_true", help="Check or install the optional Gemini provider.")
    parser.add_argument("--pdf", action="store_true", help="Check or install optional PDF import support.")
    args = parser.parse_args()
    requirements_path = (
        GEMINI_REQUIREMENTS_PATH if args.ai_gemini
        else PDF_REQUIREMENTS_PATH if args.pdf
        else DICTIONARY_REQUIREMENTS_PATH if args.dictionary
        else IMAGE_REQUIREMENTS_PATH if args.image
        else DEFAULT_REQUIREMENTS_PATH
    )

    if args.install:
        result = subprocess.run(install_command(requirements_path), check=False)
        return result.returncode
    if args.check:
        missing = missing_requirements(requirements_path)
        if not missing:
            print("All BookBuddy dependencies are installed.")
            return 0
        print("Missing dependencies: " + ", ".join(item.display for item in missing))
        _print_manual_install_instructions(requirements_path)
        return 1

    try:
        ensure_dependencies(
            "BookBuddy optional Gemini provider" if args.ai_gemini
            else "BookBuddy optional PDF import" if args.pdf
            else "BookBuddy optional dictionary subsystem" if args.dictionary
            else "BookBuddy optional image pipeline" if args.image
            else "BookBuddy",
            requirements_path,
        )
    except DependencyInstallationRequired:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
