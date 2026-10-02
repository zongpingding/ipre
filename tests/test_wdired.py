"""Batch rename validation, interruption and recovery edge cases."""

import os
import shlex
import socket
import stat
import unittest

from support import IpreTestCase


class WdiredTests(IpreTestCase):
    def edit_rows(self, targets, rows, expected_returncode=0, script=""):
        editor = self.root / "row-editor"
        editor.write_text('#!/usr/bin/env python3\nimport os,pathlib,sys\n'
                          'pathlib.Path(sys.argv[-1]).write_bytes(os.fsencode(os.environ["IPRE_TEST_ROWS"]))\n')
        editor.chmod(0o755)
        self.env["EDITOR"] = str(editor)
        self.env["IPRE_TEST_ROWS"] = rows
        return self.backend("ipre_action_wdired", *map(str, targets), tty=True,
                            expected_returncode=expected_returncode,
                            script='read() { :; }; ' + script + 'source "$1" "${@:2}"')

    def test_every_stage_and_commit_failure_restores_a_three_way_cycle(self):
        # Fail before AND after each actual rename, including the last commit.
        for after in (False, True):
            for step in range(1, 7):
                with self.subTest(after=after, step=step):
                    for name in ("one", "two", "three"):
                        (self.cwd / name).write_text(name)
                    injected = f'(( ++move_count == {step} )) && return 1; '
                    operation = 'command mv "$@" || return; '
                    self.batch_rename(
                        ["one", "two", "three"], {1: "two", 2: "three", 3: "one"},
                        expected_returncode=1,
                        script='local move_count=0; mv() { '
                               + (operation + injected if after else injected + operation)
                               + 'return 0; }; ',
                    )
                    for name in ("one", "two", "three"):
                        self.assertEqual((self.cwd / name).read_text(), name)
                    self.assertEqual({p.name for p in self.cwd.iterdir()}, {"one", "two", "three"})
                    self.assertFalse((self.state / "FOCUS").exists())

    def test_ctrl_c_can_close_the_error_screen_after_rollback(self):
        (self.cwd / "one").write_text("one")
        result = self.backend(
            "ipre_action_wdired", "one", tty=True, expected_returncode=1,
            script='editor_wrapper() { printf "[1]\\tnew-one\\n" > "${@[-1]}"; }; '
                   'EDITOR=editor_wrapper; mv() { return 1; }; source "$1" "${@:2}"',
            responses=((b"Press any key to return...", b"\x03"),),
        )
        self.assertEqual((self.cwd / "one").read_text(), "one")
        self.assert_ui_is_scoped(result)

    def test_directory_file_and_symlink_cycle_preserves_types_and_contents(self):
        (self.cwd / "directory").mkdir()
        (self.cwd / "directory" / "child").write_text("child")
        (self.cwd / "file").write_text("file")
        (self.cwd / "link").symlink_to("absent")
        self.batch_rename(["directory", "file", "link"], {1: "file", 2: "link", 3: "directory"})
        self.assertEqual((self.cwd / "file" / "child").read_text(), "child")
        self.assertEqual((self.cwd / "link").read_text(), "file")
        self.assertEqual(os.readlink(self.cwd / "directory"), "absent")
        self.assertEqual({p.name for p in self.cwd.iterdir()}, {"directory", "file", "link"})

    def test_hardlinks_fifo_and_socket_keep_their_identity(self):
        (self.cwd / "one").write_text("linked data")
        os.link(self.cwd / "one", self.cwd / "two")
        os.mkfifo(self.cwd / "fifo")
        sock = socket.socket(socket.AF_UNIX)
        self.addCleanup(sock.close)
        sock.bind(str(self.cwd / "socket"))
        names = ["one", "two", "fifo", "socket"]
        before = [(self.cwd / name).lstat() for name in names]
        self.batch_rename(names, {i: "new-" + name for i, name in enumerate(names, 1)})
        for name, original in zip(names, before):
            moved = (self.cwd / ("new-" + name)).lstat()
            self.assertEqual((moved.st_dev, moved.st_ino, stat.S_IFMT(moved.st_mode)),
                             (original.st_dev, original.st_ino, stat.S_IFMT(original.st_mode)))
            self.assertFalse((self.cwd / name).exists())
        self.assertEqual((self.cwd / "new-one").stat().st_nlink, 2)

    def test_duplicate_and_aliased_sources_are_one_editor_row(self):
        (self.cwd / "real").mkdir()
        (self.cwd / "real" / "one").write_text("one")
        (self.cwd / "alias").symlink_to("real", target_is_directory=True)
        self.edit_rows(["real/one", "./real/one", self.cwd / "real/one", "alias/one"],
                       "[1]\trenamed\n")
        self.assertEqual((self.cwd / "real" / "renamed").read_text(), "one")
        self.assertFalse((self.cwd / "real" / "one").exists())

    def test_reordered_rows_and_edited_comments_keep_source_bindings(self):
        for name in ("one", "two", "three"):
            (self.cwd / name).write_text(name)
        self.edit_rows(["one", "two", "three"],
                       "# [2] Source: /misleading\n[3]\tnew-three\n[1]\tnew-one\n[2]\t\n")
        self.assertEqual((self.cwd / "new-one").read_text(), "one")
        self.assertEqual((self.cwd / "two").read_text(), "two")
        self.assertEqual((self.cwd / "new-three").read_text(), "three")

    def test_crlf_editor_output_does_not_add_carriage_returns_to_names(self):
        (self.cwd / "one").write_text("one")
        (self.cwd / "two").write_text("two")
        self.edit_rows(["one", "two"], "# edited on Windows\r\n\r\n[1]\tnew-one\r\n[2]\tnew-two\\r\r\n")
        self.assertEqual((self.cwd / "new-one").read_text(), "one")
        self.assertEqual((self.cwd / "new-two\r").read_text(), "two")

    def test_cancel_and_unchanged_edits_do_not_move_or_create_focus(self):
        (self.cwd / "one").write_text("one")
        for rows in ("", "# cancelled\n\n", "[1]\t\n", "[1]\tone\n", "[1]\t./one\n"):
            with self.subTest(rows=rows):
                self.edit_rows(["one"], rows, script='mv() { return 99; }; ')
                self.assertEqual((self.cwd / "one").read_text(), "one")
                self.assertEqual({p.name for p in self.cwd.iterdir()}, {"one"})
                self.assertFalse((self.state / "FOCUS").exists())

    def test_invalid_escapes_and_malformed_rows_abort_the_entire_batch(self):
        for name in ("one", "two"):
            (self.cwd / name).write_text(name)
        bad_rows = ["[2] two", "[2]\tbad\\", "[2]\tbad\\q", "[2]\tbad\\x0G",
                    "[2]\tbad\\x1", "[2]\tbad\\x00", "[0]\ttwo", "[3]\ttwo",
                    "[-1]\ttwo", "[1+1]\ttwo", "[2]\ttwo\nnot a comment"]
        for row in bad_rows:
            with self.subTest(row=row):
                self.edit_rows(["one", "two"], "[1]\tnew-one\n" + row + "\n", expected_returncode=1)
                self.assertEqual({p.name for p in self.cwd.iterdir()}, {"one", "two"})
                self.assertEqual((self.cwd / "one").read_text(), "one")
                self.assertEqual((self.cwd / "two").read_text(), "two")

    def test_special_names_and_non_utf8_bytes_round_trip_without_evaluation(self):
        special = " -$()`'\";[]*?# 中文 " + "".join(chr(c) for c in range(1, 32)) + "\x7f\\"
        source = self.cwd / ("old" + special)
        source.write_text("special")
        self.batch_rename([source], {1: "new" + special})
        self.assertEqual((self.cwd / ("new" + special)).read_text(), "special")
        raw = os.fsdecode(b"old-\xff-\xfe")
        (self.cwd / raw).write_text("raw bytes")
        self.edit_rows([raw], "[1]\tnew-\\xFF-\\xFE\n")
        target = self.cwd / os.fsdecode(b"new-\xff-\xfe")
        self.assertEqual(target.read_text(), "raw bytes")
        self.assertFalse((self.cwd / raw).exists())

    def test_existing_dangling_link_and_blocked_parent_are_conflicts(self):
        (self.cwd / "one").write_text("one")
        (self.cwd / "blocked").write_text("blocker")
        (self.cwd / "dangling").symlink_to("absent")
        (self.cwd / "loop").symlink_to("loop")
        for target in ("dangling", "blocked/new", "dangling/new", "loop/new", "one/child", "new/", ".", "/"):
            with self.subTest(target=target):
                self.batch_rename(["one"], {1: target}, expected_returncode=1)
                self.assertEqual((self.cwd / "one").read_text(), "one")
                self.assertEqual((self.cwd / "blocked").read_text(), "blocker")
                self.assertEqual(os.readlink(self.cwd / "dangling"), "absent")
                self.assertEqual(list(self.cwd.glob(".ipre-rename.*")), [])

    def test_multiple_targets_create_shared_missing_parents(self):
        for name in ("one", "two"):
            (self.cwd / name).write_text(name)
        self.batch_rename(["one", "two"], {1: "new/deep/one", 2: "new/deep/two"})
        self.assertEqual((self.cwd / "new/deep/one").read_text(), "one")
        self.assertEqual((self.cwd / "new/deep/two").read_text(), "two")
        self.assertEqual({p.name for p in self.cwd.iterdir()}, {"new"})

    def test_current_directory_ancestor_and_root_are_never_renamed(self):
        (self.cwd / "one").write_text("one")
        for source in (self.cwd, self.root, "/"):
            with self.subTest(source=source):
                self.edit_rows([source], "[1]\tunwanted\n", expected_returncode=1)
                self.assertEqual((self.cwd / "one").read_text(), "one")
                self.assertEqual(list(self.cwd.glob(".ipre-rename.*")), [])

    def test_missing_source_aborts_valid_sources_before_editor(self):
        (self.cwd / "one").write_text("one")
        marker = self.root / "editor-called"
        self.env["IPRE_TEST_MARKER"] = str(marker)
        self.batch_rename(["one", "missing"], {1: "new-one"}, expected_returncode=1,
                          script='editor_wrapper() { touch "$IPRE_TEST_MARKER"; }; EDITOR=editor_wrapper; ')
        self.assertFalse(marker.exists())
        self.assertEqual({p.name for p in self.cwd.iterdir()}, {"one"})

    def test_failed_editor_and_removed_edit_file_leave_sources_and_no_temp_files(self):
        (self.cwd / "one").write_text("one")
        temp_dir = self.root / "editor-temp"
        temp_dir.mkdir()
        self.env["TMPDIR"] = str(temp_dir)
        for body in ('return 7', 'command rm -- "${@[-1]}"'):
            with self.subTest(body=body):
                self.batch_rename(["one"], {1: "renamed"}, expected_returncode=1,
                                  script='editor_wrapper() { "$IPRE_TEST_EDITOR" "$@"; ' + body + '; }; '
                                         'IPRE_TEST_EDITOR="$EDITOR"; EDITOR=editor_wrapper; ')
                self.assertEqual((self.cwd / "one").read_text(), "one")
                self.assertEqual(list(temp_dir.iterdir()), [])

    def test_signals_during_editor_cancel_without_applying_changes_or_leaking_temp_files(self):
        (self.cwd / "one").write_text("one")
        temp_dir = self.root / "editor-temp"
        temp_dir.mkdir()
        self.env["TMPDIR"] = str(temp_dir)
        for signal, code in (("INT", 130), ("TERM", 143), ("HUP", 129)):
            with self.subTest(signal=signal):
                self.batch_rename(
                    ["one"], {1: "renamed"}, expected_returncode=code,
                    script='editor_wrapper() { "$IPRE_TEST_EDITOR" "$@"; '
                           f'kill -{signal} $$; return 0; }}; '
                           'IPRE_TEST_EDITOR="$EDITOR"; EDITOR=editor_wrapper; ',
                )
                self.assertEqual({p.name for p in self.cwd.iterdir()}, {"one"})
                self.assertEqual((self.cwd / "one").read_text(), "one")
                self.assertEqual(list(temp_dir.iterdir()), [])

    def test_late_destination_collision_never_overwrites_or_moves_inside_it(self):
        for kind in ("file", "directory", "symlink", "hardlink"):
            with self.subTest(kind=kind):
                (self.cwd / "one").write_text("original")
                target = self.cwd / ("new-" + kind)
                creation = {"file": 'printf unrelated > "${@[-1]}"',
                            "directory": 'command mkdir -- "${@[-1]}"',
                            "symlink": 'command ln -s -- absent "${@[-1]}"',
                            "hardlink": 'command ln -- "${@[-2]}" "${@[-1]}"'}[kind]
                self.batch_rename(
                    ["one"], {1: target.name}, expected_returncode=1,
                    script='local move_count=0; mv() { if (( ++move_count == 2 )); then '
                           + creation + '; fi; command mv "$@"; }; ',
                )
                self.assertEqual((self.cwd / "one").read_text(), "original")
                if kind == "file":
                    self.assertEqual(target.read_text(), "unrelated")
                elif kind == "directory":
                    self.assertEqual(list(target.iterdir()), [])
                elif kind == "symlink":
                    self.assertEqual(os.readlink(target), "absent")
                else:
                    self.assertEqual(target.read_text(), "original")
                self.assertEqual(list(self.cwd.glob(".ipre-rename.*")), [])

    @unittest.skipIf(os.geteuid() == 0, "root bypasses directory permissions")
    def test_unwritable_source_or_destination_leaves_all_sources(self):
        for name in ("source", "destination"):
            (self.cwd / name).mkdir()
        (self.cwd / "source/one").write_text("one")
        for name in ("source", "destination"):
            directory = self.cwd / name
            with self.subTest(directory=name):
                directory.chmod(0o555)
                try:
                    self.batch_rename(["source/one"], {1: "../destination/new"}, expected_returncode=1)
                    self.assertEqual((self.cwd / "source/one").read_text(), "one")
                    self.assertEqual(list((self.cwd / "destination").iterdir()), [])
                    self.assertEqual(list(self.cwd.rglob(".ipre-rename.*")), [])
                finally:
                    directory.chmod(0o755)

    def test_destination_parent_replaced_after_staging_does_not_redirect_move(self):
        for replacement in ("directory", "symlink"):
            with self.subTest(replacement=replacement):
                source = self.cwd / replacement
                source.write_text("original")
                destination = self.cwd / (replacement + "-destination")
                destination.mkdir()
                other = self.cwd / (replacement + "-other")
                other.mkdir()
                self.env["IPRE_TEST_DESTINATION"] = str(destination)
                self.env["IPRE_TEST_OTHER"] = str(other)
                replace = ('command mkdir -- "$IPRE_TEST_DESTINATION"; ' if replacement == "directory"
                           else 'command ln -s -- "$IPRE_TEST_OTHER" "$IPRE_TEST_DESTINATION"; ')
                self.batch_rename(
                    [source], {1: str(destination / "renamed")}, expected_returncode=1,
                    script='local move_count=0; mv() { command mv "$@" || return; '
                           'if (( ++move_count == 1 )); then '
                           'command mv -- "$IPRE_TEST_DESTINATION" "$IPRE_TEST_DESTINATION-backup"; '
                           + replace + 'fi; }; ',
                )
                self.assertEqual(source.read_text(), "original")
                self.assertEqual(list(destination.iterdir()), [])
                self.assertEqual(list(other.iterdir()), [])
                self.assertEqual(list(self.cwd.glob(".ipre-rename.*")), [])

    def test_parent_replaced_during_commit_reports_failure_and_keeps_recovery_map(self):
        (self.cwd / "one").write_text("original")
        (self.cwd / "destination").mkdir()
        result = self.batch_rename(
            ["one"], {1: "destination/new"}, expected_returncode=1,
            script='local move_count=0; mv() { if (( ++move_count == 2 )); then '
                   'command mv -- destination destination-backup; command mkdir destination; '
                   'fi; command mv "$@"; }; ',
        )
        # This race happens inside mv, after the preflight check. It cannot be
        # undone safely through the replaced parent; report the surviving path.
        self.assertEqual((self.cwd / "destination/new").read_text(), "original")
        self.assertEqual(list((self.cwd / "destination-backup").iterdir()), [])
        recovery_dirs = list(self.cwd.glob(".ipre-rename.*"))
        self.assertEqual(len(recovery_dirs), 1)
        self.assertIn(str(self.cwd / "destination/new"),
                      (recovery_dirs[0] / "recovery.txt").read_text())
        self.assertIn("Rollback failed", result.stdout)
        self.assertFalse((self.state / "FOCUS").exists())

    def test_source_parent_replaced_with_alias_during_edit_is_rejected(self):
        (self.cwd / "parent").mkdir()
        (self.cwd / "parent/one").write_text("original")
        self.batch_rename(
            ["parent/one"], {1: "renamed"}, expected_returncode=1,
            script='editor_wrapper() { "$IPRE_TEST_EDITOR" "$@"; '
                   'command mv -- parent moved-parent; command ln -s -- moved-parent parent; }; '
                   'IPRE_TEST_EDITOR="$EDITOR"; EDITOR=editor_wrapper; ',
        )
        self.assertEqual((self.cwd / "moved-parent/one").read_text(), "original")
        self.assertFalse((self.cwd / "moved-parent/renamed").exists())
        self.assertEqual(list(self.cwd.rglob(".ipre-rename.*")), [])

    def test_replaced_created_parent_is_not_removed_by_rollback_cleanup(self):
        for name in ("one", "two"):
            (self.cwd / name).write_text(name)
        self.batch_rename(
            ["one", "two"], {1: "created/new-one", 2: "new-two"}, expected_returncode=1,
            script='local move_count=0; mv() { if (( ++move_count == 2 )); then '
                   'command mv -- created moved-created; command mkdir -- created; return 1; '
                   'fi; command mv "$@"; }; ',
        )
        for name in ("one", "two"):
            self.assertEqual((self.cwd / name).read_text(), name)
        self.assertTrue((self.cwd / "created").is_dir())
        self.assertTrue((self.cwd / "moved-created").is_dir())
        self.assertEqual(list(self.cwd.glob(".ipre-rename.*")), [])

    def test_replaced_staging_directory_is_not_cleaned_as_our_own(self):
        (self.cwd / "one").write_text("original")
        result = self.batch_rename(
            ["one"], {1: "new-one"}, expected_returncode=1,
            script='mv() { command mv "$@" || return; local stage="${@[-1]:h}"; '
                   'command mv -- "$stage" saved-stage; command mkdir -- "$stage"; '
                   'printf unrelated > "$stage/recovery.txt"; }; ',
        )
        self.assertEqual((self.cwd / "saved-stage/item").read_text(), "original")
        self.assertTrue((self.cwd / "saved-stage/recovery.txt").is_file())
        replacement_dirs = list(self.cwd.glob(".ipre-rename.*"))
        self.assertEqual(len(replacement_dirs), 1)
        self.assertEqual((replacement_dirs[0] / "recovery.txt").read_text(), "unrelated")
        self.assertIn("Staging directory changed", result.stdout)
        self.assertFalse((self.state / "FOCUS").exists())

    def test_prepare_failures_remove_only_created_empty_directories(self):
        (self.cwd / "one").write_text("one")
        (self.cwd / "two").write_text("two")
        failures = [
            'mkdir() { [[ "${@[-1]:t}" == deep ]] && return 1; command mkdir "$@"; }; ',
            'mktemp() { [[ "$1" == -d ]] && return 1; command mktemp "$@"; }; ',
            'mktemp() { if [[ "$1" == -d ]]; then local -a stages=(.ipre-rename.*(N)); '
            '(( ${#stages} )) && return 1; fi; '
            'command mktemp "$@"; }; ',
        ]
        marker = self.root / "move-called"
        self.env["IPRE_TEST_MARKER"] = str(marker)
        for script in failures:
            with self.subTest(script=script):
                self.batch_rename(["one", "two"], {1: "created/deep/new-one", 2: "new-two"},
                                  expected_returncode=1,
                                  script=script + 'mv() { touch "$IPRE_TEST_MARKER"; command mv "$@"; }; ')
                self.assertFalse(marker.exists())
                self.assertEqual({p.name for p in self.cwd.iterdir()}, {"one", "two"})
                for name in ("one", "two"):
                    self.assertEqual((self.cwd / name).read_text(), name)

    @unittest.skipIf(os.geteuid() == 0, "root bypasses directory permissions")
    def test_recovery_map_write_failure_happens_before_any_source_moves(self):
        (self.cwd / "one").write_text("one")
        self.batch_rename(
            ["one"], {1: "new-one"}, expected_returncode=1,
            script='mktemp() { if [[ "$1" == -d ]]; then local directory; '
                   'directory=$(command mktemp "$@") || return; command chmod 500 -- "$directory"; '
                   'print -r -- "$directory"; else command mktemp "$@"; fi; }; ',
        )
        self.assertEqual((self.cwd / "one").read_text(), "one")
        self.assertEqual({p.name for p in self.cwd.iterdir()}, {"one"})

    def test_committed_destination_replaced_before_rollback_is_not_touched(self):
        for name in ("one", "two"):
            (self.cwd / name).write_text(name)
        result = self.batch_rename(
            ["one", "two"], {1: "new-one", 2: "new-two"}, expected_returncode=1,
            script='local move_count=0; mv() { if (( ++move_count == 4 )); then '
                   'command mv -- new-one saved-one; printf unrelated > new-one; return 1; '
                   'fi; command mv "$@"; }; ',
        )
        self.assertEqual((self.cwd / "saved-one").read_text(), "one")
        self.assertEqual((self.cwd / "two").read_text(), "two")
        self.assertEqual((self.cwd / "new-one").read_text(), "unrelated")
        self.assertFalse((self.cwd / "new-two").exists())
        recovery_dirs = list(self.cwd.glob(".ipre-rename.*"))
        self.assertEqual(len(recovery_dirs), 1)
        self.assertTrue((recovery_dirs[0] / "recovery.txt").is_file())
        self.assertIn("Rollback failed", result.stdout)

    def test_unexpected_staging_payload_keeps_its_recovery_map(self):
        (self.cwd / "one").write_text("original")
        result = self.batch_rename(
            ["one"], {1: "renamed"}, expected_returncode=1,
            script='mv() { printf unexpected > "${@[-1]}"; return 1; }; ',
        )
        self.assertEqual((self.cwd / "one").read_text(), "original")
        recovery_dirs = list(self.cwd.glob(".ipre-rename.*"))
        self.assertEqual(len(recovery_dirs), 1)
        self.assertEqual((recovery_dirs[0] / "item").read_text(), "unexpected")
        self.assertTrue((recovery_dirs[0] / "recovery.txt").exists())
        self.assertIn(str(recovery_dirs[0]), result.stdout)

    def test_known_conflict_aborts_other_valid_rows(self):
        for name in ("one", "two", "taken"):
            (self.cwd / name).write_text(name)
        self.batch_rename(["one", "two"], {1: "renamed", 2: "taken"}, expected_returncode=1)
        self.assertEqual((self.cwd / "one").read_text(), "one")
        self.assertEqual((self.cwd / "two").read_text(), "two")
        self.assertEqual((self.cwd / "taken").read_text(), "taken")
        self.assertFalse((self.cwd / "renamed").exists())

    def test_aliases_of_one_destination_are_rejected_before_staging(self):
        real = self.cwd / "real"
        real.mkdir()
        (self.cwd / "alias").symlink_to(real, target_is_directory=True)
        for name in ("one", "two"):
            (self.cwd / name).write_text(name)
        marker = self.root / "move-was-called"
        self.env["IPRE_TEST_MOVE_MARKER"] = str(marker)
        self.batch_rename(
            ["one", "two"], {1: "real/result", 2: "alias/result"}, expected_returncode=1,
            script='mv() { touch "$IPRE_TEST_MOVE_MARKER"; command mv "$@"; }; ',
        )
        self.assertFalse(marker.exists())
        self.assertEqual((self.cwd / "one").read_text(), "one")
        self.assertEqual((self.cwd / "two").read_text(), "two")

    def test_source_replaced_during_edit_is_not_renamed(self):
        (self.cwd / "one").write_text("original")
        self.batch_rename(
            ["one"], {1: "renamed"}, expected_returncode=1,
            script='editor_wrapper() { "$IPRE_TEST_EDITOR" "$@"; '
                   'command mv -- one original-backup; printf replacement > one; }; '
                   'IPRE_TEST_EDITOR="$EDITOR"; EDITOR=editor_wrapper; ',
        )
        self.assertEqual((self.cwd / "one").read_text(), "replacement")
        self.assertEqual((self.cwd / "original-backup").read_text(), "original")
        self.assertFalse((self.cwd / "renamed").exists())

    def test_symlink_retargeted_during_edit_is_not_renamed(self):
        (self.cwd / "target-one").write_text("one")
        (self.cwd / "target-two").write_text("two")
        link = self.cwd / "link"
        link.symlink_to("target-one")
        self.batch_rename(
            ["link"], {1: "renamed-link"}, expected_returncode=1,
            script='editor_wrapper() { "$IPRE_TEST_EDITOR" "$@"; '
                   'rm -- link; ln -s -- target-two link; }; '
                   'IPRE_TEST_EDITOR="$EDITOR"; EDITOR=editor_wrapper; ',
        )
        self.assertEqual(os.readlink(link), "target-two")
        self.assertEqual((self.cwd / "target-one").read_text(), "one")
        self.assertEqual((self.cwd / "target-two").read_text(), "two")
        self.assertFalse((self.cwd / "renamed-link").exists())

    def test_signals_after_each_staging_and_commit_move_restore_sources(self):
        for name in ("one", "two"):
            (self.cwd / name).write_text(name)
        for signal, code in (("INT", 130), ("TERM", 143), ("HUP", 129)):
            for move_number in range(1, 5):
                with self.subTest(signal=signal, move_number=move_number):
                    self.batch_rename(
                        ["one", "two"], {1: "new-one", 2: "new-two"}, expected_returncode=code,
                        script='local move_count=0; mv() { command mv "$@" || return; '
                               f'(( ++move_count )); if (( move_count == {move_number} )); '
                               f'then kill -{signal} $$; fi; }}; ',
                    )
                    for name in ("one", "two"):
                        self.assertEqual((self.cwd / name).read_text(), name)
                    self.assertEqual({p.name for p in self.cwd.iterdir()}, {"one", "two"})

    def test_failure_reported_after_completed_move_is_rolled_back(self):
        (self.cwd / "one").write_text("original")
        self.batch_rename(
            ["one"], {1: "renamed"}, expected_returncode=1,
            script='local move_count=0; mv() { command mv "$@" || return; '
                   '(( ++move_count )); (( move_count != 2 )); }; ',
        )
        self.assertEqual((self.cwd / "one").read_text(), "original")
        self.assertFalse((self.cwd / "renamed").exists())

    def test_directory_and_unchanged_selected_child_are_rejected(self):
        (self.cwd / "parent").mkdir()
        (self.cwd / "parent" / "child").write_text("child")
        self.batch_rename(["parent", "parent/child"], {1: "new-parent"}, expected_returncode=1)
        self.assertEqual((self.cwd / "parent" / "child").read_text(), "child")
        self.assertFalse((self.cwd / "new-parent").exists())

    def test_alias_into_source_directory_cannot_hide_self_descendant_move(self):
        (self.cwd / "parent").mkdir()
        (self.cwd / "parent" / "child").write_text("child")
        (self.cwd / "alias").symlink_to("parent", target_is_directory=True)
        self.batch_rename(["parent"], {1: "alias/nested/new-parent"}, expected_returncode=1)
        self.assertEqual((self.cwd / "parent" / "child").read_text(), "child")
        self.assertEqual(list((self.cwd / "parent").iterdir()), [self.cwd / "parent" / "child"])

    def test_symlink_leaf_is_moved_without_moving_its_target(self):
        (self.cwd / "target").write_text("target")
        (self.cwd / "link").symlink_to("target")
        (self.cwd / "dangling").symlink_to("absent")
        self.batch_rename(["link", "dangling"], {1: "new-link", 2: "new-dangling"})
        self.assertEqual(os.readlink(self.cwd / "new-link"), "target")
        self.assertEqual(os.readlink(self.cwd / "new-dangling"), "absent")
        self.assertEqual((self.cwd / "target").read_text(), "target")

    def test_three_way_cycle_keeps_each_files_contents(self):
        for name in ("one", "two", "three"):
            (self.cwd / name).write_text(name)
        self.batch_rename(["one", "two", "three"], {1: "two", 2: "three", 3: "one"})
        for name, contents in (("one", "three"), ("two", "one"), ("three", "two")):
            self.assertEqual((self.cwd / name).read_text(), contents)

    def test_new_empty_parent_directories_are_removed_on_rollback(self):
        for name in ("one", "two"):
            (self.cwd / name).write_text(name)
        self.batch_rename(
            ["one", "two"], {1: "created/deep/new-one", 2: "new-two"}, expected_returncode=1,
            script='mv() { [[ "${@[-1]:t}" == new-two ]] && return 1; command mv "$@"; }; ',
        )
        self.assertEqual({p.name for p in self.cwd.iterdir()}, {"one", "two"})
        self.assertEqual((self.cwd / "one").read_text(), "one")
        self.assertEqual((self.cwd / "two").read_text(), "two")

    def test_failed_rollback_retains_payload_and_recovery_map_without_overwriting(self):
        for name in ("one", "two"):
            (self.cwd / name).write_text(name)
        result = self.batch_rename(
            ["one", "two"], {1: "new-one", 2: "new-two"}, expected_returncode=1,
            script='mv() { if [[ "${@[-1]:t}" == new-two ]]; then '
                   'printf unrelated > "$IPRE_CWD/one"; return 1; fi; command mv "$@"; }; ',
        )
        self.assertEqual((self.cwd / "one").read_text(), "unrelated")
        self.assertEqual((self.cwd / "two").read_text(), "two")
        recovery_dirs = list(self.cwd.glob(".ipre-rename.*"))
        self.assertEqual(len(recovery_dirs), 1)
        self.assertEqual((recovery_dirs[0] / "item").read_text(), "one")
        self.assertIn(str(self.cwd / "one"), (recovery_dirs[0] / "recovery.txt").read_text())
        self.assertIn("Rollback failed", result.stdout)
        self.assertFalse((self.state / "FOCUS").exists())

    def test_cross_filesystem_plan_is_rejected_before_staging(self):
        (self.cwd / "one").write_text("one")
        target_dir = self.cwd / "other-device"
        target_dir.mkdir()
        self.env["IPRE_TEST_OTHER_DEVICE"] = str(target_dir)
        self.batch_rename(
            ["one"], {1: "other-device/new-one"}, expected_returncode=1,
            script='zstat() { builtin zstat "$@" || return; '
                   'if [[ "${@[-1]}" == "$IPRE_TEST_OTHER_DEVICE" ]]; then '
                   '(( attrs[device]+=1 )); fi; }; ',
        )
        self.assertEqual((self.cwd / "one").read_text(), "one")
        self.assertEqual(list(target_dir.iterdir()), [])
        self.assertEqual(list(self.cwd.glob(".ipre-rename.*")), [])

    def test_quoted_editor_command_receives_options_without_vim_arguments(self):
        (self.cwd / "one").write_text("one")
        editor = self.root / "editor with spaces"
        editor.write_text(
            '#!/usr/bin/env python3\nimport pathlib,sys\n'
            'assert sys.argv[1:-1] == ["--custom-option"]\n'
            'p=pathlib.Path(sys.argv[-1])\n'
            'p.write_text(p.read_text().replace("[1]\\tone", "[1]\\trenamed"))\n'
        )
        editor.chmod(0o755)
        self.env["EDITOR"] = shlex.quote(str(editor)) + " --custom-option"
        self.backend("ipre_action_wdired", "one", tty=True)
        self.assertEqual((self.cwd / "renamed").read_text(), "one")

    def test_invalid_ids_missing_rows_and_duplicate_rows_never_move_files(self):
        for name in ("one", "two"):
            (self.cwd / name).write_text(name)
        editor = self.root / "row-editor"
        editor.write_text('#!/usr/bin/env python3\nimport os,pathlib,sys\n'
                          'pathlib.Path(sys.argv[-1]).write_text(os.environ["IPRE_TEST_ROWS"])\n')
        editor.chmod(0o755)
        self.env["EDITOR"] = str(editor)
        for rows in ("[01]\tnew-one\n[2]\ttwo\n", "[1]\tnew-one\n", "[1]\tone\n[1]\tnew-one\n[2]\ttwo\n",
                     "[" + "9" * 100 + "]\tnew-one\n[2]\ttwo\n"):
            with self.subTest(rows=rows):
                self.env["IPRE_TEST_ROWS"] = rows
                self.backend("ipre_action_wdired", "one", "two", tty=True, expected_returncode=1,
                             script='read() { :; }; source "$1" "${@:2}"')
                self.assertEqual((self.cwd / "one").read_text(), "one")
                self.assertEqual((self.cwd / "two").read_text(), "two")
