"""
Run this before building wizard.spec. Copies the built companion
exes, uninstaller, and extension folder into installer/resources/,
which wizard.spec then bundles into the packaged installer exe.

Usage (from installer/):
    python prepare_resources.py
"""

import shutil
import sys
from pathlib import Path


def main():
    installer_dir = Path(__file__).resolve().parent
    project_root = installer_dir.parent

    companion_dist = project_root / "companion" / "dist"
    extension_dir = project_root / "extension"

    resources_dir = installer_dir / "resources"

    if resources_dir.exists():
        shutil.rmtree(resources_dir)

    resources_dir.mkdir(parents=True)

    # --------------------------------------------------------------
    # Companion executables
    # --------------------------------------------------------------

    required_exes = (
        "cleandrop-host.exe",
        "cleandrop-scheduler.exe",
    )

    for name in required_exes:
        src = companion_dist / name

        if not src.exists():
            print(f"ERROR: {src} not found.")
            print(
                "Build both exes first: "
                "pyinstaller cleandrop-host.spec && "
                "pyinstaller cleandrop-scheduler.spec"
            )
            sys.exit(1)

        shutil.copy2(
            src,
            resources_dir / name,
        )

        print(f"Copied {name}")

    # --------------------------------------------------------------
    # Uninstaller
    # --------------------------------------------------------------

    uninstaller_dist = installer_dir / "dist"
    uninstaller_src = (
        uninstaller_dist / "CleanDropUninstall.exe"
    )

    if not uninstaller_src.exists():
        print(
            f"ERROR: {uninstaller_src} not found."
        )

        print(
            "Build CleanDropUninstall.exe first with:"
        )

        print(
            "  pyinstaller uninstall.spec"
        )

        sys.exit(1)

    shutil.copy2(
        uninstaller_src,
        resources_dir / "CleanDropUninstall.exe",
    )

    print("Copied CleanDropUninstall.exe")

    # --------------------------------------------------------------
    # Chrome extension
    # --------------------------------------------------------------

    if not extension_dir.exists():
        print(
            f"ERROR: {extension_dir} not found."
        )
        sys.exit(1)

    shutil.copytree(
        extension_dir,
        resources_dir / "extension",
    )

    print("Copied extension/")

    # --------------------------------------------------------------
    # Done
    # --------------------------------------------------------------

    print(
        f"\nResources ready at: {resources_dir}"
    )

    print(
        "Now run: pyinstaller wizard.spec"
    )


if __name__ == "__main__":
    main()