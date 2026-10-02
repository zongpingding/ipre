"""Temporary fixtures and helpers shared by regression suites."""

import os
import json
import fcntl
import pathlib
import pty
import re
import select
import struct
import subprocess
import tempfile
import termios
import time
import unittest
from urllib.parse import quote_from_bytes


ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / "ipre_backend"


def path_key(value):
    return quote_from_bytes(os.fsencode(value), safe="/-._~")


def editor_text(value):
    text = str(value)
    text = text.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
    return "".join(f"\\x{ord(c):02X}" if ord(c) < 32 or ord(c) == 127 else c for c in text)


class IpreTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ipre-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.cwd = self.root / "cwd"
        self.cwd.mkdir()
        self.trash = self.root / "trash"
        self.trash.mkdir()
        self.state = self.root / "state"
        self.state.mkdir()
        defaults = {
            "CWD": str(self.cwd),
            "STATE": "all",
            "HIDDEN": "true",
            "SORT": "name",
            "TARGETS": "",
            "CLIP": "",
            "SELECT": "",
            "RAM_DEPTH": "0",
            "PAGE": "1",
            "PAGE_MAX": "",
            "LAST": "",
            "RAM_LIST": "",
            "RAM_POS": "",
            "NOTICE": "",
            "BOOKMARKS": "",
            "VIEW": "compact",
            "BACK": "",
            "FORWARD": "",
        }
        # Keep each test independent of the invoking ipre session and fzf config.
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("IPRE_", "FZF_"))}
        runtime = self.root / "xdg-runtime"
        runtime.mkdir()
        self.env.update(
            XDG_CACHE_HOME=str(self.root / "xdg-cache"),
            XDG_DATA_HOME=str(self.root / "xdg-data"),
            XDG_RUNTIME_DIR=str(runtime),
            FZF_DEFAULT_OPTS="",
            FZF_DEFAULT_OPTS_FILE="",
            IPRE_ICONS="0",
            IPRE_USE_LS="0",
            IPRE_FD_CMD_STR="fd --follow -I .",
            IPRE_BACKEND_CMD=str(BACKEND),
            IPRE_TRASH_DIR=str(self.trash),
            IPRE_RAM_DIR=str(self.state),
            PATH=f"{ROOT}:{self.env['PATH']}",
            TERM="xterm",
        )
        for name, value in defaults.items():
            path = self.state / name
            path.write_text(value + "\n" if value else "")
            self.env[f"IPRE_{name}_FILE"] = str(path)
        self.env["IPRE_RAM_FOCUS_FILE"] = str(self.state / "FOCUS")

    def backend(self, action, *args, script=None, tty=False, expected_returncode=0, responses=()):
        if script is None:
            argv = [str(BACKEND), action, *args]
        else:
            argv = ["zsh", "-fc", script, "-", str(BACKEND), action, *args]
        if not tty:
            return subprocess.run(
                argv, env=self.env, text=True, capture_output=True, timeout=5
            )
        pid, master = pty.fork()
        if pid == 0:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 120, 0, 0))
            os.execvpe(argv[0], argv, self.env)
        output = bytearray()
        pending = list(responses)
        deadline = time.monotonic() + 5
        status = None
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], 0.05)
            if ready:
                try:
                    chunk = os.read(master, 65536)
                    output.extend(chunk)
                    # Answer fzf's cursor query as a terminal at the cleared origin.
                    if b"\x1b[6n" in chunk:
                        os.write(master, b"\x1b[1;1R")
                    if pending and pending[0][0] in output:
                        os.write(master, pending.pop(0)[1])
                except OSError:
                    pass
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                break
        else:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
            self.fail(f"{action} timed out: {output[-500:]!r}")
        # A process can exit before the final screen cleanup has been read.
        while select.select([master], [], [], 0)[0]:
            try:
                chunk = os.read(master, 65536)
            except OSError:
                break
            if not chunk:
                break
            output.extend(chunk)
        os.close(master)
        returncode = os.waitstatus_to_exitcode(status)
        self.assertEqual(returncode, expected_returncode, output[-1000:])
        return subprocess.CompletedProcess(
            argv, returncode, output.decode(errors="replace"), ""
        )

    def delete_to_trash(self, *args, script="", expected_returncode=0):
        return self.backend(
            "ipre_action_delete",
            *args,
            script=(
                'read() { ans=y; }; clear() { :; }; sleep() { :; }; '
                'date() { if [[ "$1" == "+%s" ]]; then print -r -- 1790841600; '
                'else command date "$@"; fi; }; '
                + script
                + 'source "$1" "${@:2}"'
            ),
            tty=True,
            expected_returncode=expected_returncode,
        )

    def restore_trash(self, script="", expected_returncode=0):
        return self.backend(
            "ipre_action_probe",
            script=(
                'ipre_action_probe() { :; }; fzf() { cat; }; '
                'clear() { :; }; sleep() { :; }; '
                + script
                + 'source "$1" "$2"; ipre_palette_do_trash_restore'
            ),
            tty=True,
            expected_returncode=expected_returncode,
        )

    def assert_ui_is_scoped(self, result, expected_screens=1):
        active = False
        screens = 0
        for part in re.split(r"(\x1b\[\?1049[hl])", result.stdout):
            if part == "\x1b[?1049h":
                self.assertFalse(active, "nested alternate screens")
                active = True
                screens += 1
            elif part == "\x1b[?1049l":
                self.assertTrue(active, "unbalanced alternate screen exit")
                active = False
            elif not active:
                self.assertEqual(part, "", "output leaked onto the main screen")
        self.assertFalse(active, "alternate screen left active")
        self.assertEqual(screens, expected_screens)

    def rename_item(self, target, new_name, expected_returncode=0):
        self.env["IPRE_TEST_NEW_NAME"] = new_name
        result = self.backend(
            "ipre_action_rename", str(target),
            script='vared() { val="$IPRE_TEST_NEW_NAME"; }; '
            'clear() { :; }; sleep() { :; }; source "$1" "$2" "$3"',
            tty=True, expected_returncode=expected_returncode,
        )
        self.assertEqual(result.returncode, expected_returncode, result.stderr)
        return result

    def batch_rename(self, targets, new_names, script="", expected_returncode=0):
        replacements = {
            f"[{i}]\t{editor_text(pathlib.Path(target).name)}":
            f"[{i}]\t{editor_text(new_names[i])}"
            for i, target in enumerate(targets, 1) if i in new_names
        }
        self.env["IPRE_TEST_RENAME_ROWS"] = json.dumps(replacements)
        editor = self.root / "batch-editor"
        editor.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "p = pathlib.Path(sys.argv[-1])\n"
            "s = p.read_text()\n"
            "for old, new in json.loads(os.environ['IPRE_TEST_RENAME_ROWS']).items():\n"
            "    s = s.replace(old, new)\n"
            "p.write_text(s)\n"
        )
        editor.chmod(0o755)
        self.env["EDITOR"] = str(editor)
        return self.backend(
            "ipre_action_wdired", *map(str, targets),
            script='read() { return 0; }; ' + script + 'source "$1" "${@:2}"',
            tty=True, expected_returncode=expected_returncode,
        )
