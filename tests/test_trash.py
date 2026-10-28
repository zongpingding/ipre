"""Regression tests for trash."""

import os
import shutil

from support import IpreTestCase, path_key


class TrashTests(IpreTestCase):
    def test_same_named_deletions_are_restored_independently(self):
        for name in ("a", "b"):
            folder = self.cwd / name
            folder.mkdir()
            (folder / "report.txt").write_text(name)
        result = self.delete_to_trash("a/report.txt", "b/report.txt")
        self.assert_ui_is_scoped(result)
        self.assertFalse((self.cwd / "a/report.txt").exists())
        self.assertFalse((self.cwd / "b/report.txt").exists())
        entries = list(self.trash.iterdir())
        self.assertEqual(len(entries), 2)
        self.assertEqual(
            {child.read_text() for entry in entries for child in (entry / "payload").iterdir()},
            {"a", "b"},
        )
        result = self.restore_trash()
        self.assert_ui_is_scoped(result)
        for name in ("a", "b"):
            self.assertEqual((self.cwd / name / "report.txt").read_text(), name)
        self.assertEqual(list(self.cwd.glob("report*.txt")), [])
        self.assertEqual(list(self.trash.iterdir()), [])

    def test_trash_repeated_deletions_in_same_second_keep_both_contents(self):
        source = self.cwd / "report.txt"
        for content in ("first", "second"):
            source.write_text(content)
            self.delete_to_trash("report.txt")
            self.assertFalse(source.exists())
        entries = list(self.trash.iterdir())
        self.assertEqual(len(entries), 2)
        self.assertEqual(
            {(entry / "payload/report.txt").read_text() for entry in entries},
            {"first", "second"},
        )

    def test_trash_concurrent_deletions_keep_both_contents(self):
        for name in ("a", "b"):
            folder = self.cwd / name
            folder.mkdir()
            (folder / "report.txt").write_text(name)
        self.backend(
            "ipre_action_probe",
            script=(
                'ipre_action_probe() { :; }; read() { ans=y; }; '
                'clear() { :; }; sleep() { :; }; '
                'date() { print -r -- 1790841600; }; '
                'source "$1" "$2"; '
                'ipre_action_delete a/report.txt & first=$!; '
                'ipre_action_delete b/report.txt & second=$!; '
                'wait "$first" || exit $?; wait "$second"'
            ),
            tty=True,
        )
        entries = list(self.trash.iterdir())
        self.assertEqual(len(entries), 2)
        self.assertEqual(
            {(entry / "payload/report.txt").read_text() for entry in entries}, {"a", "b"}
        )
        self.assertFalse((self.cwd / "a/report.txt").exists())
        self.assertFalse((self.cwd / "b/report.txt").exists())

    def test_trash_entry_creation_failure_preserves_source(self):
        source = self.cwd / "report.txt"
        source.write_text("payload")
        result = self.delete_to_trash(
            "report.txt", script='mktemp() { return 1; }; ', expected_returncode=1
        )
        self.assertEqual(source.read_text(), "payload")
        self.assertEqual(list(self.trash.iterdir()), [])
        self.assertIn("Moved to trash: 0 item(s); failed: 1.", result.stdout)
        self.assert_ui_is_scoped(result)

    def test_trash_partial_move_failure_preserves_source_and_other_entry(self):
        for name in ("a", "b"):
            folder = self.cwd / name
            folder.mkdir()
            (folder / "report.txt").write_text(name)
        result = self.delete_to_trash(
            "a/report.txt",
            "b/report.txt",
            script=(
                'mv() { if [[ "$2" == "b/report.txt" ]]; then return 1; fi; '
                'command mv "$@"; }; '
            ),
            expected_returncode=1,
        )
        self.assertFalse((self.cwd / "a/report.txt").exists())
        self.assertEqual((self.cwd / "b/report.txt").read_text(), "b")
        entries = list(self.trash.iterdir())
        self.assertEqual(len(entries), 1)
        self.assertEqual((entries[0] / "payload/report.txt").read_text(), "a")
        self.assertIn("Moved to trash: 1 item(s); failed: 1.", result.stdout)
        self.assert_ui_is_scoped(result)

    def test_trash_same_named_directories_are_restored_independently(self):
        for name in ("a", "b"):
            folder = self.cwd / name / "bundle"
            folder.mkdir(parents=True)
            (folder / "report.txt").write_text(name)
        self.delete_to_trash("a/bundle/", "b/bundle/")
        entries = list(self.trash.iterdir())
        self.assertEqual(len(entries), 2)
        self.assertEqual(
            {(entry / "payload/bundle/report.txt").read_text() for entry in entries},
            {"a", "b"},
        )
        self.restore_trash()
        for name in ("a", "b"):
            self.assertEqual((self.cwd / name / "bundle/report.txt").read_text(), name)
        self.assertEqual(list(self.trash.iterdir()), [])

    def test_trash_preserves_original_names_and_dangling_symlinks(self):
        names = [
            ".hidden", "report.txt___123", "odd\nname\t%09.txt", "trailing\n",
            "-option", "a" * 255, "origin", "payload",
        ]
        for name in names:
            (self.cwd / name).write_text(name)
        link = self.cwd / "dangling"
        link.symlink_to("missing")
        self.delete_to_trash(*names, "dangling")
        self.assertEqual(list(self.cwd.iterdir()), [])
        entries = list(self.trash.iterdir())
        self.assertEqual(len(entries), len(names) + 1)
        self.assertEqual(
            {child.name for entry in entries for child in (entry / "payload").iterdir()},
            set(names) | {"dangling"},
        )
        self.restore_trash()
        for name in names:
            self.assertEqual((self.cwd / name).read_text(), name)
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), "missing")
        self.assertEqual(list(self.trash.iterdir()), [])

    def test_trash_restore_failure_keeps_entry_for_retry(self):
        source = self.cwd / "report.txt"
        source.write_text("payload")
        self.delete_to_trash("report.txt")
        result = self.restore_trash(
            script='mv() { return 1; }; ', expected_returncode=1
        )
        self.assertFalse(source.exists())
        entries = list(self.trash.iterdir())
        self.assertEqual(len(entries), 1)
        self.assertEqual((entries[0] / "payload/report.txt").read_text(), "payload")
        self.assertIn("Restored: 0 item(s); failed: 1.", result.stdout)
        self.assert_ui_is_scoped(result)
        self.restore_trash()
        self.assertEqual(source.read_text(), "payload")
        self.assertEqual(list(self.trash.iterdir()), [])

    def test_trash_restore_uses_original_path_after_changing_directory(self):
        folder = self.cwd / "aaa"
        folder.mkdir()
        source = folder / "bb.txt"
        source.write_text("payload")
        self.delete_to_trash("aaa/bb.txt")
        entry = next(self.trash.iterdir())
        self.assertEqual((entry / "origin").read_bytes(), os.fsencode(source) + b"\0")
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        (self.state / "CWD").write_text(path_key(elsewhere) + "\n")
        result = self.restore_trash()
        self.assertEqual(source.read_text(), "payload")
        self.assertEqual(list(elsewhere.iterdir()), [])
        self.assertEqual(list(self.trash.iterdir()), [])
        self.assert_ui_is_scoped(result)

    def test_trash_restore_recreates_missing_original_parent(self):
        folder = self.cwd / "aaa/bbb"
        folder.mkdir(parents=True)
        source = folder / "report.txt"
        source.write_text("payload")
        self.delete_to_trash(str(source))
        folder.rmdir()
        folder.parent.rmdir()
        self.restore_trash()
        self.assertEqual(source.read_text(), "payload")
        self.assertEqual(list(self.trash.iterdir()), [])

    def test_trash_restore_conflict_keeps_both_items_in_original_parent(self):
        folder = self.cwd / "aaa"
        folder.mkdir()
        source = folder / "report.txt"
        source.write_text("payload")
        self.delete_to_trash("aaa/report.txt")
        source.symlink_to("missing")
        self.restore_trash()
        self.assertTrue(source.is_symlink())
        self.assertEqual(os.readlink(source), "missing")
        self.assertEqual((folder / "report_restored1.txt").read_text(), "payload")
        self.assertFalse((self.cwd / "report_restored1.txt").exists())
        self.assertEqual(list(self.trash.iterdir()), [])

    def test_trash_restore_blocked_parent_preserves_entry(self):
        folder = self.cwd / "aaa"
        folder.mkdir()
        source = folder / "report.txt"
        source.write_text("payload")
        self.delete_to_trash("aaa/report.txt")
        folder.rmdir()
        folder.write_text("blocking file")
        result = self.restore_trash(expected_returncode=1)
        self.assertEqual(folder.read_text(), "blocking file")
        entries = list(self.trash.iterdir())
        self.assertEqual(len(entries), 1)
        self.assertEqual((entries[0] / "payload/report.txt").read_text(), "payload")
        self.assertEqual((entries[0] / "origin").read_bytes(), os.fsencode(source) + b"\0")
        self.assert_ui_is_scoped(result)

    def test_trash_origin_write_failure_preserves_source(self):
        source = self.cwd / "report.txt"
        source.write_text("payload")
        result = self.delete_to_trash(
            "report.txt",
            script=(
                "printf() { if [[ \"$1\" == '%s\\0' ]]; then return 1; fi; "
                'builtin printf "$@"; }; '
            ),
            expected_returncode=1,
        )
        self.assertEqual(source.read_text(), "payload")
        self.assertEqual(list(self.trash.iterdir()), [])
        self.assert_ui_is_scoped(result)

    def test_trash_cancel_and_empty_restore_leave_no_main_screen_output(self):
        source = self.cwd / "report.txt"
        source.write_text("payload")
        result = self.delete_to_trash("report.txt", script='read() { ans=n; }; ')
        self.assertEqual(source.read_text(), "payload")
        self.assertEqual(list(self.trash.iterdir()), [])
        self.assert_ui_is_scoped(result)
        result = self.restore_trash()
        self.assertIn("Trash bin is empty.", result.stdout)
        self.assert_ui_is_scoped(result)
        self.delete_to_trash("report.txt")
        result = self.restore_trash(script='fzf() { cat >/dev/null; return 130; }; ')
        self.assertFalse(source.exists())
        self.assertEqual(len(list(self.trash.iterdir())), 1)
        self.assert_ui_is_scoped(result)

    def test_trash_empty_output_stays_in_alternate_screen(self):
        (self.cwd / "report.txt").write_text("payload")
        self.delete_to_trash("report.txt")
        result = self.backend(
            "ipre_action_probe",
            script='ipre_action_probe() { :; }; sleep() { :; }; '
            'source "$1" "$2"; ipre_palette_do_trash_empty',
            tty=True,
        )
        self.assertEqual(list(self.trash.iterdir()), [])
        self.assertIn("Trash bin emptied.", result.stdout)
        self.assert_ui_is_scoped(result)

    def test_trash_restore_with_real_fzf_keeps_ui_in_one_alternate_screen(self):
        if not shutil.which("fzf"):
            self.skipTest("fzf is needed for the interactive restore")
        (self.cwd / "report.txt").write_text("payload")
        self.delete_to_trash("report.txt")
        result = self.restore_trash(
            script='fzf() { command fzf "$@" --bind load:select-all+accept; }; '
        )
        self.assertEqual((self.cwd / "report.txt").read_text(), "payload")
        self.assertEqual(list(self.trash.iterdir()), [])
        self.assert_ui_is_scoped(result)

    def test_trash_command_palette_with_real_fzf_leaves_no_main_screen_output(self):
        if not shutil.which("fzf"):
            self.skipTest("fzf is needed for the interactive command palette")
        (self.cwd / "report.txt").write_text("payload")
        self.delete_to_trash("report.txt")
        result = self.backend(
            "ipre_action_command_palette",
            script=(
                'sleep() { :; }; fzf() { '
                'if [[ "$*" == *"Command > "* ]]; then '
                'command fzf "$@" --query=restore --sync --bind load:accept; '
                'else command fzf "$@" --bind load:select-all+accept; fi; }; '
                'source "$1" "$2"'
            ),
            tty=True,
        )
        self.assertEqual((self.cwd / "report.txt").read_text(), "payload")
        self.assertEqual(list(self.trash.iterdir()), [])
        self.assert_ui_is_scoped(result, expected_screens=2)

    def test_newline_filename_can_be_deleted_and_restored(self):
        name = "odd\nname.txt"
        source = self.cwd / name
        source.write_text("payload")
        encoded = path_key(source)
        record = encoded + "\todd\\nname.txt"
        self.backend(
            "ipre_action_delete",
            "--records", record,
            script='read() { ans=y; }; clear() { :; }; '
            'sleep() { :; }; source "$1" "${@:2}"',
            tty=True,
        )
        self.assertFalse(source.exists())
        self.backend(
            "ipre_action_probe",
            script='ipre_action_probe() { :; }; fzf() { cat; }; '
            'clear() { :; }; sleep() { :; }; '
            'source "$1" "$2"; ipre_palette_do_trash_restore',
            tty=True,
        )
        self.assertEqual(source.read_text(), "payload")
