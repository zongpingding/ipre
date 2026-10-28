"""Export the current live-grep matches without losing location identities."""

import json
import os
import shlex
import shutil

from support import IpreTestCase, editor_text, path_key


class GrepExportTests(IpreTestCase):
    def setUp(self):
        super().setUp()
        self.env["XDG_STATE_HOME"] = str(self.root / "xdg-state")
        self.env["NVIM_LOG_FILE"] = str(self.root / "nvim.log")
        self.copied = self.root / "copied locations"
        copier = self.root / "clipboard program"
        copier.write_text('#!/usr/bin/env python3\nimport pathlib,sys\n'
                          'pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())\n')
        copier.chmod(0o755)
        self.env["CLIPBOARD"] = shlex.quote(str(copier)) + " " + shlex.quote(str(self.copied))

    def record(self, path, line=1, column=1):
        # Display text deliberately cannot be parsed as a filename/location.
        return f"{path_key(path)}\t{line}\t{column}\t\x1b[31mignored:99:42:body\\text\x1b[0m\n"

    def export(self, mode, matched, selected="", selected_count=0, expected_returncode=0):
        all_file = self.root / "all matches"
        selected_file = self.root / "selected matches"
        all_file.write_text(matched)
        selected_file.write_text(selected)
        self.env["FZF_SELECT_COUNT"] = str(selected_count)
        result = self.backend("ipre_action_rg_export", mode, str(selected_file), str(all_file),
                              tty=True, expected_returncode=expected_returncode)
        self.assertEqual(list(self.state.glob("rg-export.*")), [])
        return result

    def prepare_editor(self, name="nvim", commands=""):
        executable = shutil.which(name)
        if not executable:
            self.skipTest(f"{name} is needed to check real Quickfix behavior")
        directory = self.root / "editor bin"
        directory.mkdir(exist_ok=True)
        wrapper = directory / name
        capture = self.root / "capture.vim"
        self.env["IPRE_TEST_QF_LOG"] = str(self.root / "quickfix.json")
        self.env["IPRE_TEST_CURSOR_LOG"] = str(self.root / "cursor.json")
        self.env["IPRE_TEST_CAPTURE"] = str(capture)
        self.env["IPRE_TEST_EDITOR_EXECUTABLE"] = executable
        capture.write_text(
            "call writefile([json_encode(map(getqflist(), "
            "{_, v -> {'filename': fnamemodify(bufname(v.bufnr), ':p'), 'lnum': v.lnum, 'col': v.col}}))], $IPRE_TEST_QF_LOG)\n"
            "call writefile([json_encode([expand('%:p'), line('.'), col('.'), "
            "len(filter(getwininfo(), 'v:val.quickfix'))])], $IPRE_TEST_CURSOR_LOG)\n"
            + commands + "\nqa!\n"
        )
        flags = ["--headless"] if name == "nvim" else ["-es"]
        wrapper.write_text(
            '#!/usr/bin/env python3\nimport os,sys\n'
            'exe=os.environ["IPRE_TEST_EDITOR_EXECUTABLE"]\n'
            f'os.execv(exe, [exe, *{flags!r}, "-u", "NONE", "-i", "NONE", "-n", '
            '*sys.argv[1:], "-S", os.environ["IPRE_TEST_CAPTURE"]])\n'
        )
        wrapper.chmod(0o755)
        self.env["EDITOR"] = shlex.quote(str(wrapper)) + " -N"

    def test_copy_uses_marked_items_or_all_matches_and_preserves_multiple_locations(self):
        first = self.cwd / "chapters" / "first:file.tex"
        second = self.cwd / "second.tex"
        rows = self.record(first, 102, 5) + self.record(second, 654, 7) + self.record(second, 739, 46)
        # fzf's + placeholder supplies the cursor row even with no marks.
        self.export("copy", rows, self.record(first, 102, 5))
        self.assertEqual(self.copied.read_text(),
                         "chapters/first:file.tex:102:5:\nsecond.tex:654:7:\nsecond.tex:739:46:\n")
        self.export("copy", rows, self.record(second, 739, 46), selected_count=1)
        self.assertEqual(self.copied.read_text(), "second.tex:739:46:\n")

    def test_copy_from_symlink_directory_escapes_path_controls_but_ignores_body(self):
        real = self.root / "real"
        real.mkdir()
        link = self.cwd / "alias"
        link.symlink_to(real, target_is_directory=True)
        (self.state / "CWD").write_text(path_key(link) + "\n")
        name = "quote'colon:back\\tab\tline\n.txt"
        self.export("copy", self.record(real / name, 2, 8))
        self.assertEqual(self.copied.read_text(), editor_text(name) + ":2:8:\n")

    def test_empty_and_invalid_results_do_not_touch_clipboard(self):
        self.copied.write_text("existing")
        self.export("copy", "")
        self.assertIn("No matching results", (self.state / "rg_notice").read_text())
        for invalid in ("bad row\n", "/bad%GG\t1\t1\ttext\n", "/tmp/x\t1|quit\t1\ttext\n",
                        "/tmp/x\t0\t1\ttext\n", "/tmp/x\t1\t-1\ttext\n"):
            with self.subTest(invalid=invalid):
                self.export("copy", self.record(self.cwd / "valid") + invalid, expected_returncode=1)
                self.assertEqual(self.copied.read_text(), "existing")

    def test_clipboard_failure_and_unsupported_editor_are_reported(self):
        source = self.cwd / "one"
        source.write_text("needle")
        for command in ("ipre-missing-clipboard-command", "false"):
            with self.subTest(command=command):
                self.env["CLIPBOARD"] = command
                self.export("copy", self.record(source), expected_returncode=1)
                self.assertRegex((self.state / "rg_notice").read_text(), "unavailable|Failed")
        self.env["EDITOR"] = "nano"
        self.export("edit", self.record(source), expected_returncode=1)
        self.assertIn("Quickfix requires", (self.state / "rg_notice").read_text())
        self.export("edit", self.record(self.cwd / "missing"), expected_returncode=1)
        self.assertIn("missing or unreadable", (self.state / "rg_notice").read_text())

    def test_real_editors_load_exact_paths_and_locations_and_can_edit_successive_files(self):
        first = self.cwd / 'first:"quote\'\\tab\tline\n.tex'
        second = self.cwd / '中文 $(touch INJECTED).tex'
        for name in ("nvim", "vim"):
            with self.subTest(editor=name):
                first.write_text("one\n  two\nthree\n")
                second.write_text("other\n")
                self.prepare_editor(name, commands=
                                    "call setline('.', 'changed first')\nupdate\n"
                                    "cnext\ncall setline('.', 'changed second match')\nupdate\n"
                                    "cnfile\ncall setline('.', 'changed next file')\nupdate\n")
                self.export("edit", self.record(first, 2, 3) + self.record(first, 3, 1) + self.record(second))
                entries = json.loads((self.root / "quickfix.json").read_text())
                self.assertEqual(entries, [dict(filename=str(first), lnum=2, col=3),
                                           dict(filename=str(first), lnum=3, col=1),
                                           dict(filename=str(second), lnum=1, col=1)])
                self.assertEqual(json.loads((self.root / "cursor.json").read_text()), [str(first), 2, 3, 1])
                self.assertEqual(first.read_text(), "one\nchanged first\nchanged second match\n")
                self.assertEqual(second.read_text(), "changed next file\n")
                self.assertFalse((self.cwd / "INJECTED").exists())

    def test_quickfix_preserves_non_utf8_filename_bytes(self):
        source = self.cwd / os.fsdecode(b"raw-\xff-\xfe.tex")
        source.write_text("needle\n")
        self.prepare_editor()
        raw_log = self.root / "raw-path"
        self.env["IPRE_TEST_RAW_LOG"] = str(raw_log)
        (self.root / "capture.vim").write_text("call writefile([expand('%:p')], $IPRE_TEST_RAW_LOG, 'b')\nqa!\n")
        self.export("edit", self.record(source))
        self.assertEqual(raw_log.read_bytes(), os.fsencode(source))

    def test_editor_failure_cleans_temporary_files_and_reports_status(self):
        source = self.cwd / "one"
        source.write_text("needle\n")
        editor = self.root / "nvim"
        editor.write_text('#!/bin/sh\nexit 7\n')
        editor.chmod(0o755)
        self.env["EDITOR"] = str(editor)
        self.export("edit", self.record(source), expected_returncode=1)
        self.assertIn("Editor exited with an error", (self.state / "rg_notice").read_text())
        self.assertEqual(source.read_text(), "needle\n")

    def test_real_fzf_empty_results_leave_clipboard_untouched(self):
        self.copied.write_text("existing")
        self.backend("ipre_action_live_grep", tty=True,
                     responses=((b"Ripgrep", b"\x1by"), (b"No matching results", b"\x1b")))
        self.assertEqual(self.copied.read_text(), "existing")
        self.assertEqual(list(self.state.glob("rg-export.*")), [])

    def test_real_fzf_copies_all_matches_including_offscreen_results_and_keeps_picker_open(self):
        source = self.cwd / "many.tex"
        source.write_text("needle\n" * 40)
        self.backend("ipre_action_live_grep", tty=True,
                     responses=((b"Ripgrep", b"needle"), (b"40/40", b"\x1by"),
                                (b"Copied 40 location(s)", b"\x1b")))
        self.assertCountEqual(self.copied.read_text().splitlines(), [f"many.tex:{i}:1:" for i in range(1, 41)])
        self.assertFalse((self.state / "FOCUS").exists())
        self.assertFalse((self.state / "rg_notice").exists())

    def test_real_fzf_marks_take_priority_over_all_matches(self):
        (self.cwd / "one.tex").write_text("needle\n" * 3)
        self.backend("ipre_action_live_grep", tty=True,
                     responses=((b"Ripgrep", b"needle"), (b"3/3", b"\t\x1by"),
                                (b"Copied 1 location(s)", b"\x1b")))
        self.assertEqual(len(self.copied.read_text().splitlines()), 1)
        self.assertRegex(self.copied.read_text(), r"^one\.tex:[123]:1:\n$")

    def test_real_fzf_edits_fuzzy_matches_then_returns_with_filter_intact(self):
        keep = self.cwd / "keep:file.tex"
        keep.write_text("needle\nneedle\n")
        (self.cwd / "other.tex").write_text("needle\nneedle\n")
        self.prepare_editor(commands="call setline('.', 'edited')\nupdate\n")
        self.backend("ipre_action_live_grep", tty=True,
                     responses=((b"Ripgrep", b"needle"), (b"4/4", b"\x1bf"),
                                (b"Fuzzy", b"keep"), (b"2/4", b"\x1be"),
                                (b"Returned from Quickfix", b"\x1by"),
                                (b"Copied 2 location(s)", b"\x1b")))
        self.assertEqual(keep.read_text(), "edited\nneedle\n")
        self.assertEqual((self.cwd / "other.tex").read_text(), "needle\nneedle\n")
        self.assertEqual(len(json.loads((self.root / "quickfix.json").read_text())), 2)
        self.assertCountEqual(self.copied.read_text().splitlines(), ["keep:file.tex:1:1:", "keep:file.tex:2:1:"])
        self.assertEqual(list(self.state.glob("rg-export.*")), [])
        self.assertFalse((self.state / "FOCUS").exists())
