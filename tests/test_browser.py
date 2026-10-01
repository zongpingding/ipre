"""Regression tests for browser."""

import os
import json
import fcntl
import pty
import select
import signal
import shutil
import struct
import subprocess
import termios
import time
from urllib.parse import unquote

from support import IpreTestCase, ROOT, BACKEND, path_key


class BrowserTests(IpreTestCase):
    def test_listing_keeps_arrows_symlinks_and_control_characters(self):
        if not shutil.which("fd"):
            self.skipTest("fd is needed for listing")
        names = ["a -> b.txt", "my doc.pdf", "tab\tname%09", "new\nline"]
        for name in names:
            (self.cwd / name).write_text(name)
        (self.cwd / "link").symlink_to("my doc.pdf")
        for use_ls, icons in [("0", "0"), ("0", "1"), ("1", "0")]:
            with self.subTest(use_ls=use_ls, icons=icons):
                self.env["IPRE_USE_LS"] = use_ls
                self.env["IPRE_ICONS"] = icons
                result = self.backend("ipre_action_run")
                self.assertEqual(result.returncode, 0, result.stderr)
                paths = {
                    unquote(line.split("\t", 1)[0])
                    for line in result.stdout.splitlines()
                }
                self.assertEqual(paths, {str(p) for p in self.cwd.iterdir()})

    def test_real_fzf_passes_the_hidden_encoded_field_to_copy(self):
        if not shutil.which("fzf"):
            self.skipTest("fzf is needed for the interactive field selection")
        source = self.cwd / "a -> b\t%0A\n"
        source.write_text("selected")
        self.env["IPRE_TEST_RECORD"] = self.backend("ipre_action_run").stdout.strip("\n")
        self.env["FZF_DEFAULT_OPTS"] = ""
        self.env["FZF_DEFAULT_OPTS_FILE"] = ""
        self.backend(
            "ipre_action_probe",
            script=(
                'ipre_action_probe() { :; }; source "$1" "$2"; '
                'printf "%s\\n" "$IPRE_TEST_RECORD" | command fzf '
                '--delimiter=$\'\\t\' --with-nth=2 '
                '--bind \'load:execute-silent("$IPRE_BACKEND_CMD" ipre_action_copy --encoded {1})+accept\''
            ),
            tty=True,
        )
        self.assertEqual((self.state / "CLIP").read_text(), f"COPY\n{path_key(source)}\n")

    def test_real_main_reload_and_failed_paste_in_empty_directory(self):
        if not shutil.which("fzf") or not shutil.which("fd") or os.geteuid() == 0:
            self.skipTest("real fzf/fd and non-root directory permissions are required")
        source = self.cwd / "victimarrow -> %0A\n"
        source.write_text("payload")
        destination = self.cwd / "destination"
        destination.mkdir(mode=0o555)
        self.addCleanup(destination.chmod, 0o755)
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        preview = bin_dir / "pre"
        preview.write_text(
            '#!/usr/bin/env python3\nimport json,os,pathlib,sys\n'
            'pathlib.Path(os.environ["IPRE_TEST_PRE_LOG"]).write_text(json.dumps(sys.argv[1:]))\n'
        )
        preview.chmod(0o755)
        for name in ("cache", "data", "runtime"):
            (self.root / name).mkdir()
        env = dict(self.env, PATH=f"{bin_dir}:{self.env['PATH']}",
                   XDG_CACHE_HOME=str(self.root / "cache"), XDG_DATA_HOME=str(self.root / "data"),
                   XDG_RUNTIME_DIR=str(self.root / "runtime"), FZF_DEFAULT_OPTS="", FZF_DEFAULT_OPTS_FILE="",
                   IPRE_TEST_PRE_LOG=str(self.root / "preview-log"))
        pid, master = pty.fork()
        if pid == 0:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 160, 0, 0))
            os.execvpe(str(ROOT / "ipre"), [str(ROOT / "ipre"), str(self.cwd), "--depth", "1"], env)
        output = bytearray()

        def until(check):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.02)[0]:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        if check():
                            return
                        raise
                    output.extend(chunk)
                    if b"\x1b[6n" in chunk:
                        os.write(master, b"\x1b[1;1R")
                if check():
                    return
            self.fail(f"fzf interaction timed out: {output[-1000:]!r}")

        def highlighted(path):
            try:
                return json.loads((self.root / "preview-log").read_text())[0] == str(path)
            except (OSError, ValueError, IndexError):
                return False

        try:
            until(lambda: b"victimarrow" in output)
            state = next((self.root / "runtime").iterdir())
            os.write(master, b"victimarrow")
            until(lambda: highlighted(source))
            os.write(master, b"\x1bx")
            expected = f"CUT\n{path_key(source)}\n"
            until(lambda: (state / "fzf_clip").read_text() == expected)
            os.write(master, b"\x15destination")
            until(lambda: highlighted(destination))
            os.write(master, b"\x1b[C")
            until(lambda: b"Empty directory / No matches" in output)
            self.assertEqual((state / "fzf_cwd").read_text(), path_key(destination) + "\n")
            self.assertEqual((state / "ipre_fzf_list").read_text(), "")
            os.write(master, b"\x1bv")
            until(lambda: b"Paste: 1 failed" in output)
            self.assertEqual((state / "fzf_clip").read_text(), expected)
            self.assertFalse((state / "ipre_fzf_focus").exists())
            self.assertEqual(source.read_text(), "payload")
            os.write(master, b"\x11")
            until(lambda: not state.exists())
        finally:
            if os.waitpid(pid, os.WNOHANG)[0] == 0:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
            os.close(master)

    def test_listing_sort_modes_keep_directory_first_and_preserve_names(self):
        (self.state / "RAM_DEPTH").write_text("1\n")
        folder = self.cwd / "z -> folder"
        folder.mkdir()
        first = self.cwd / "a -> first.txt"
        second = self.cwd / "b second.py"
        first.write_text("small")
        second.write_text("large" * 10)
        os.utime(first, (1000, 1000))
        os.utime(second, (2000, 2000))
        for mode, order in [("name", [first, second]), ("time", [second, first]), ("size", [second, first]), ("ext", [second, first])]:
            with self.subTest(mode=mode):
                (self.state / "SORT").write_text(mode + "\n")
                result = self.backend("ipre_action_run")
                self.assertEqual(result.returncode, 0, result.stderr)
                keys = [row.split("\t", 1)[0] for row in result.stdout.splitlines()]
                self.assertEqual(keys, [path_key(p) for p in [folder, *order]])

    def test_multiple_search_roots_with_controls_keep_exact_paths(self):
        roots = [self.root / "one -> %0A", self.root / "two\nroot"]
        for folder in roots:
            folder.mkdir()
            (folder / "report\t.txt").write_text("selected")
        (self.cwd / "excluded.txt").write_text("excluded")
        (self.state / "TARGETS").write_text("".join(path_key(folder) + "\n" for folder in roots))
        result = self.backend("ipre_action_run")
        self.assertEqual(result.returncode, 0, result.stderr)
        keys = {row.split("\t", 1)[0] for row in result.stdout.splitlines()}
        self.assertEqual(keys, {path_key(folder / "report\t.txt") for folder in roots})

    def test_main_control_paths_and_legacy_bookmark_migration(self):
        folder = self.cwd / "dir -> %0A\n"
        folder.mkdir()
        source = folder / "a -> %09\t\\file\n"
        source.write_text("selected")
        legacy_path = self.cwd / "literal%0A"
        legacy_path.write_text("literal")
        data = self.root / "data/ipre"
        data.mkdir(parents=True)
        legacy = data / "bookmarks"
        legacy.write_text(str(legacy_path) + "\n")
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fzf = bin_dir / "fzf"
        fzf.write_text(
            "#!/usr/bin/env python3\n"
            "import os, pathlib, sys\n"
            "for line in sys.stdin:\n"
            "    if line.split('\\t', 1)[0] == os.environ['IPRE_TEST_SELECTED_KEY']:\n"
            "        if os.environ.get('IPRE_TEST_EXIT_CWD'):\n"
            "            pathlib.Path(os.environ['IPRE_FORCE_CD_FILE']).write_text('1')\n"
            "        sys.stdout.write(line)\n"
            "        break\n"
        )
        fzf.chmod(0o755)
        editor = bin_dir / "editor"
        editor.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "pathlib.Path(os.environ['IPRE_TEST_EDITOR_LOG']).write_text("
            "json.dumps({'args': sys.argv[1:], 'cwd': os.getcwd()}))\n"
        )
        editor.chmod(0o755)
        env = dict(self.env)
        env.update(
            PATH=f"{bin_dir}:{env['PATH']}", EDITOR=str(editor),
            XDG_CACHE_HOME=str(self.root / "cache"),
            XDG_DATA_HOME=str(self.root / "data"),
            XDG_RUNTIME_DIR=str(self.root / "runtime"),
            IPRE_TEST_SELECTED_KEY=path_key(source),
            IPRE_TEST_EDITOR_LOG=str(self.root / "editor-log"),
        )
        (self.root / "runtime").mkdir()
        result = subprocess.run([str(ROOT / "ipre"), str(folder)], env=env, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        opened = json.loads((self.root / "editor-log").read_text())
        self.assertEqual(opened, {"args": [str(source)], "cwd": str(folder)})
        self.assertEqual((data / "bookmarks.paths-v1").read_text(), path_key(legacy_path) + "\n")
        self.assertEqual(legacy.read_text(), str(legacy_path) + "\n")
        self.assertEqual(list((self.root / "runtime").iterdir()), [])
        env["IPRE_TEST_EXIT_CWD"] = "1"
        cwd_output = self.root / "cwd-output"
        result = subprocess.run(
            [str(ROOT / "ipre"), str(folder), f"--cwd-file={cwd_output}"],
            env=env, capture_output=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(cwd_output.read_bytes(), os.fsencode(folder))

    def test_navigation_focus_uses_the_record_path(self):
        folder = self.cwd / "space folder"
        folder.mkdir()
        (self.cwd / "other.txt").write_text("x")
        (self.state / "CWD").write_text(path_key(folder) + "\n")
        (self.state / "RAM_DEPTH").write_text("1\n")
        result = self.backend("ipre_action_left")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.state / "CWD").read_text().strip(), path_key(self.cwd))
        records = (self.state / "RAM_LIST").read_text().splitlines()
        position = int((self.state / "RAM_POS").read_text().strip())
        self.assertEqual(records[position - 1].split("\t", 1)[0], path_key(folder))

    def test_default_depth_is_one(self):
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fzf = bin_dir / "fzf"
        fzf.write_text(
            "#!/usr/bin/env python3\n"
            "import os, pathlib, sys\n"
            "pathlib.Path(os.environ['IPRE_TEST_DEPTH_LOG']).write_text("
            "pathlib.Path(os.environ['IPRE_RAM_DEPTH_FILE']).read_text())\n"
            "sys.stdin.read()\n"
        )
        fzf.chmod(0o755)
        (self.root / "runtime").mkdir()
        env = dict(self.env)
        env.update(
            PATH=f"{bin_dir}:{env['PATH']}",
            IPRE_TEST_DEPTH_LOG=str(self.root / "depth-log"),
            XDG_CACHE_HOME=str(self.root / "cache"),
            XDG_DATA_HOME=str(self.root / "data"),
            XDG_RUNTIME_DIR=str(self.root / "runtime"),
        )
        result = subprocess.run(
            [str(ROOT / "ipre"), str(self.cwd)],
            env=env, text=True, capture_output=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "depth-log").read_text().strip(), "1")

    def test_unbounded_listing_streams_and_navigation_does_not_wait(self):
        early = self.cwd / "early.txt"
        late = self.cwd / "late.txt"
        early.write_text("early")
        late.write_text("late")
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fd = bin_dir / "fd"
        fd.write_text(
            "#!/usr/bin/env python3\n"
            "import sys, time\n"
            "sys.stdout.buffer.write(b'./early.txt\\0')\n"
            "sys.stdout.buffer.flush()\n"
            "time.sleep(1)\n"
            "sys.stdout.buffer.write(b'./late.txt\\0')\n"
        )
        fd.chmod(0o755)
        self.env["PATH"] = f"{bin_dir}:{self.env['PATH']}"
        self.env["IPRE_FD_CMD_STR"] = "fd ."
        started = time.monotonic()
        proc = subprocess.Popen(
            [str(BACKEND), "ipre_action_run"], env=self.env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            ready, _, _ = select.select([proc.stdout], [], [], 0.6)
            self.assertTrue(ready, "first record waited for fd to finish")
            first = proc.stdout.readline().decode()
            self.assertTrue(first.startswith(str(early) + "\t"), first)
            self.assertLess(time.monotonic() - started, 0.8)
            out, err = proc.communicate(timeout=3)
            self.assertEqual(proc.returncode, 0, err)
            self.assertIn(str(late).encode() + b"\t", out)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()

        folder = self.cwd / "nested"
        folder.mkdir()
        (self.state / "CWD").write_text(path_key(folder) + "\n")
        started = time.monotonic()
        result = self.backend("ipre_action_left")
        self.assertLess(time.monotonic() - started, 0.6)
        self.assertIn("reload(", result.stdout)
        self.assertNotIn("reload-sync", result.stdout)
        (self.state / "FOCUS").write_text(path_key(early) + "\n")
        result = self.backend("ipre_action_refresh_and_focus")
        self.assertIn("reload(", result.stdout)
        self.assertNotIn("reload-sync", result.stdout)

    def test_missing_depth_exits_instead_of_looping(self):
        cases = [(flag,) for flag in ("--depth", "-d", "--max-depth")]
        cases += [(flag, value) for flag in ("--depth", "-d", "--max-depth")
                  for value in ("", "-1", "abc", "--keep-open")]
        cases += [(f"{flag}={value}",) for flag in ("--depth", "--max-depth")
                  for value in ("", "-1", "abc")]
        for args in cases:
            with self.subTest(args=args):
                result = subprocess.run([str(ROOT / "ipre"), *args], env=self.env,
                                        text=True, capture_output=True, timeout=2)
                self.assertEqual(result.returncode, 2)
                self.assertIn("requires a non-negative integer", result.stderr.lower())
                self.assertEqual(len(result.stderr.splitlines()), 1)
