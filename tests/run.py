#!/usr/bin/env python3
"""Check dependencies and shell syntax, then run the regression suites."""

import pathlib
import shutil
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    required = ("zsh", "bash", "fd", "fzf", "rg", "file", "stat", "md5sum", "sort", "cut", "tee")
    missing = [command for command in required if shutil.which(command) is None]
    if missing:
        print("Missing test dependencies: " + ", ".join(missing), file=sys.stderr)
        return 2
    for script in ("ipre", "ipre_backend", "ipre_palette", "ipre_paths", "pre"):
        checked = subprocess.run(["zsh", "-n", str(ROOT / script)])
        if checked.returncode:
            return checked.returncode
    return subprocess.call([sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"),
                            "-v", *sys.argv[1:]], cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
