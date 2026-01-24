import os
import shutil
import sys

import PyInstaller.__main__


def build():
    print("Starting build process...")

    # Determine separator
    sep = ';' if os.name == 'nt' else ':'

    # Clean previous build
    if os.path.exists("dist"):
        print("Cleaning dist/...")
        shutil.rmtree("dist")
    if os.path.exists("build"):
        print("Cleaning build/...")
        shutil.rmtree("build")

    print("Running PyInstaller...")
    PyInstaller.__main__.run([
        'main.py',
        '--name=MeshGame',
        '--onedir',
        '--windowed',
        f'--add-data=assets{sep}assets',
        f'--add-data=scenes{sep}scenes',
        f'--add-data=config.json{sep}.',
        '--clean',
        '--noconfirm',
        # '--debug=all', # Uncomment for debugging build issues
    ])

    print("Build complete. Check dist/MeshGame/")

if __name__ == "__main__":
    # Ensure we are in the project root
    if not os.path.exists("main.py"):
        print("Error: Please run this script from the project root.")
        sys.exit(1)

    build()
