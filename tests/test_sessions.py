"""Two live frontends must own independent navigation and operation state."""

import json
import pathlib
import subprocess
import time

from support import IpreTestCase, ROOT, BACKEND, path_key


class SessionTests(IpreTestCase):
    def test_concurrent_sessions_do_not_overwrite_or_clean_up_each_other(self):
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fzf = bin_dir / "fzf"
        fzf.write_text(
            '#!/usr/bin/env python3\nimport json,os,pathlib,sys,time\n'
            'sys.stdin.read()\n'
            'ready = pathlib.Path(os.environ["IPRE_TEST_READY"])\n'
            'pending = ready.with_suffix(".tmp")\n'
            'pending.write_text(json.dumps({k:v for k,v in os.environ.items() if k.startswith("IPRE_")}))\n'
            'pending.replace(ready)\n'
            'deadline = time.monotonic() + 10\n'
            'while not ready.with_suffix(".exit").exists():\n'
            '    if time.monotonic() > deadline: sys.exit(2)\n'
            '    time.sleep(0.01)\n'
        )
        fzf.chmod(0o755)
        sessions = []
        try:
            for name in ("one", "two"):
                folder = self.root / name
                folder.mkdir()
                (folder / "nested").mkdir()
                (folder / "source.txt").write_text(name)
                ready = self.root / f"{name}.ready"
                env = dict(self.env, PATH=f"{bin_dir}:{self.env['PATH']}", IPRE_TEST_READY=str(ready))
                proc = subprocess.Popen([str(ROOT / "ipre"), str(folder)], env=env,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                sessions.append((proc, ready, folder))
                deadline = time.monotonic() + 5
                while not ready.exists():
                    self.assertIsNone(proc.poll(), "frontend exited before fzf became ready")
                    self.assertLess(time.monotonic(), deadline, "frontend did not become ready")
                    time.sleep(0.01)

            first = json.loads(sessions[0][1].read_text())
            second = json.loads(sessions[1][1].read_text())
            for key in first:
                if key.endswith("_FILE") and key != "IPRE_BOOKMARKS_FILE":
                    self.assertNotEqual(first[key], second[key], key)
            self.assertEqual(first["IPRE_BOOKMARKS_FILE"], second["IPRE_BOOKMARKS_FILE"])
            second_dir = pathlib.Path(second["IPRE_RAM_DIR"])
            before = {p.name: p.read_bytes() for p in second_dir.iterdir()}

            def action(state, command, *args):
                result = subprocess.run([str(BACKEND), command, *args], env=dict(self.env, **state),
                                        capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)

            action(first, "ipre_action_right", "--encoded", path_key(sessions[0][2] / "nested"))
            action(first, "ipre_action_cut", "--encoded", path_key(sessions[0][2] / "source.txt"))
            action(first, "ipre_action_switch")
            action(first, "ipre_action_hidden")
            action(first, "ipre_action_set_depth", "3")
            self.assertEqual({p.name: p.read_bytes() for p in second_dir.iterdir()}, before)
            self.assertEqual(pathlib.Path(first["IPRE_CWD_FILE"]).read_text(), path_key(sessions[0][2] / "nested") + "\n")
            self.assertEqual(pathlib.Path(first["IPRE_CLIP_FILE"]).read_text(), f"CUT\n{path_key(sessions[0][2] / 'source.txt')}\n")

            sessions[0][1].with_suffix(".exit").touch()
            out, err = sessions[0][0].communicate(timeout=5)
            self.assertEqual(sessions[0][0].returncode, 0, err)
            self.assertFalse(pathlib.Path(first["IPRE_RAM_DIR"]).exists())
            self.assertTrue(second_dir.is_dir())
            action(second, "ipre_action_copy", "--encoded", path_key(sessions[1][2] / "source.txt"))
            self.assertEqual(pathlib.Path(second["IPRE_CLIP_FILE"]).read_text(), f"COPY\n{path_key(sessions[1][2] / 'source.txt')}\n")
            sessions[1][1].with_suffix(".exit").touch()
            out, err = sessions[1][0].communicate(timeout=5)
            self.assertEqual(sessions[1][0].returncode, 0, err)
            self.assertFalse(second_dir.exists())
        finally:
            for proc, ready, folder in sessions:
                ready.with_suffix(".exit").touch()
                if proc.poll() is None:
                    proc.terminate()
                proc.communicate(timeout=5)
