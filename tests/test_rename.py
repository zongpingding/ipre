"""Regression tests for rename."""

import os

from support import IpreTestCase, path_key


class RenameTests(IpreTestCase):
    def test_rename_merges_saved_selection_and_updates_only_saved_paths(self):
        current = self.cwd / "current\n%name"
        current_only = self.cwd / "current only"
        other_dir = self.root / "other"
        other_dir.mkdir()
        saved = other_dir / "saved\tname"
        for source in (current, current_only, saved):
            source.write_text(source.name)
        (self.state / "SELECT").write_text(f"{path_key(current)}\n{path_key(saved)}\n")
        clip = f"COPY\n{path_key(current)}\n"
        (self.state / "CLIP").write_text(clip)
        self.backend(
            "ipre_action_rename", "--encoded", path_key(current), path_key(current_only),
            script='vared() { val="new-$val"; }; clear() { :; }; '
                   'source "$1" "${@:2}"', tty=True,
        )
        for source in (current, current_only, saved):
            self.assertEqual(source.with_name("new-" + source.name).read_text(), source.name)
            self.assertFalse(source.exists())
        self.assertEqual((self.state / "SELECT").read_text(),
                         f'{path_key(current.with_name("new-" + current.name))}\n'
                         f'{path_key(saved.with_name("new-" + saved.name))}\n')
        self.assertEqual((self.state / "CLIP").read_text(), clip)

    def test_rename_deduplicates_even_when_a_duplicate_item_is_skipped(self):
        source = self.cwd / "source"
        source.touch()
        selection = f"{path_key(source)}\n"
        (self.state / "SELECT").write_text(selection)
        for protocol, args in (("--encoded", (path_key(source), path_key(source))),
                               ("--", ("./source", str(source)))):
            with self.subTest(protocol=protocol):
                result = self.backend(
                    "ipre_action_rename", protocol, *args,
                    script='vared() { print "RENAME_PROMPT"; val=""; }; '
                           'clear() { :; }; source "$1" "${@:2}"', tty=True,
                )
                self.assertEqual(result.stdout.count("RENAME_PROMPT"), 1)
                self.assertEqual((self.state / "SELECT").read_text(), selection)

    def test_rename_buffer_only_preserves_skipped_failed_and_unprocessed_entries(self):
        names = ("success", "skip", "unchanged", "conflict", "missing", "fail", "stop", "pending")
        sources = [self.cwd / name for name in names]
        for source in sources:
            if source.name != "missing":
                source.write_text(source.name)
        (self.cwd / "taken").write_text("existing")
        (self.state / "SELECT").write_text("".join(path_key(p) + "\n" for p in sources))
        clip = f"CUT\n{path_key(sources[0])}\n"
        (self.state / "CLIP").write_text(clip)
        self.backend(
            "ipre_action_rename", "--encoded", "", tty=True, expected_returncode=1,
            script='vared() { case "${old_path:t}" in '
                   'success) val=new-success ;; skip) val="" ;; conflict) val=taken ;; '
                   'fail) val=new-fail ;; stop) val=:q ;; pending) val=new-pending ;; esac; }; '
                   'mv() { [[ "${@[-2]:t}" == fail ]] && return 1; command mv "$@"; }; '
                   'clear() { :; }; sleep() { :; }; source "$1" "${@:2}"',
        )
        expected = [self.cwd / "new-success", *sources[1:]]
        self.assertEqual((self.state / "SELECT").read_text(),
                         "".join(path_key(p) + "\n" for p in expected))
        self.assertEqual((self.cwd / "new-success").read_text(), "success")
        self.assertEqual((self.cwd / "taken").read_text(), "existing")
        for source in sources[1:]:
            if source.name != "missing":
                self.assertEqual(source.read_text(), source.name)
        self.assertEqual((self.state / "CLIP").read_text(), clip)

    def test_rename_cancel_keeps_earlier_buffer_updates(self):
        sources = [self.cwd / name for name in ("first", "second", "third")]
        for source in sources:
            source.touch()
        (self.state / "SELECT").write_text("".join(path_key(p) + "\n" for p in sources))
        self.backend(
            "ipre_action_rename", tty=True,
            script='vared() { [[ "${old_path:t}" == first ]] || return 1; val=new-first; }; '
                   'clear() { :; }; source "$1" "$2"',
        )
        self.assertEqual((self.state / "SELECT").read_text(),
                         "".join(path_key(p) + "\n" for p in [self.cwd / "new-first", *sources[1:]]))
        self.assertTrue(sources[1].exists())
        self.assertTrue(sources[2].exists())

    def test_batch_rename_handles_escaped_names_and_keeps_source_in_memory(self):
        source_name = "old -> %0A\t\\name\n"
        new_name = "new -> %09\n\\name\t"
        source = self.cwd / source_name
        source.write_text("selected")
        self.batch_rename([source_name], {1: new_name})
        target = self.cwd / new_name
        self.assertEqual(target.read_text(), "selected")
        self.assertFalse(source.exists())
        self.assertEqual((self.state / "FOCUS").read_text(), path_key(target) + "\n")

    def test_rename_stays_with_source_and_parent_move_is_relative(self):
        (self.cwd / "sub").mkdir()
        (self.cwd / "victim.txt").write_text("root")
        (self.cwd / "sub" / "victim.txt").write_text("child")
        script = (
            'vared() { val="$IPRE_TEST_NEW_NAME"; }; '
            'clear() { :; }; sleep() { :; }; source "$1" "$2" "$3"'
        )
        self.env["IPRE_TEST_NEW_NAME"] = "renamed.txt"
        result = self.backend("ipre_action_rename", "sub/victim.txt", script=script, tty=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.cwd / "victim.txt").read_text(), "root")
        self.assertEqual((self.cwd / "sub" / "renamed.txt").read_text(), "child")
        self.assertEqual((self.state / "FOCUS").read_text(), path_key(self.cwd / "sub/renamed.txt") + "\n")
        (self.state / "FOCUS").unlink()
        self.env["IPRE_TEST_NEW_NAME"] = "../moved.txt"
        result = self.backend("ipre_action_rename", "sub/renamed.txt", script=script, tty=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.cwd / "moved.txt").read_text(), "child")
        self.assertEqual((self.state / "FOCUS").read_text(), path_key(self.cwd / "moved.txt") + "\n")

    def test_batch_rename_uses_each_source_directory(self):
        (self.cwd / "same.txt").write_text("root")
        for name in ("a", "b"):
            folder = self.cwd / name
            folder.mkdir()
            (folder / "same.txt").write_text(name)
        editor = self.root / "edit-wdired"
        editor.write_text(
            "#!/usr/bin/env python3\n"
            "import pathlib, sys\n"
            "p = pathlib.Path(sys.argv[-1])\n"
            "s = p.read_text().replace('[1]\tsame.txt', "
            "'[1]\t../a_new.txt')\n"
            "s = s.replace('[2]\tsame.txt', "
            "'[2]\tb_new.txt')\n"
            "p.write_text(s)\n"
        )
        editor.chmod(0o755)
        self.env["EDITOR"] = str(editor)
        self.backend(
            "ipre_action_wdired",
            "a/same.txt",
            "b/same.txt",
            script='source "$1" "$2" "$3" "$4"',
            tty=True,
        )
        self.assertEqual((self.cwd / "a_new.txt").read_text(), "a")
        self.assertEqual((self.cwd / "b" / "b_new.txt").read_text(), "b")
        self.assertEqual((self.cwd / "same.txt").read_text(), "root")

    def test_batch_rename_can_swap_names_without_overwriting(self):
        (self.cwd / "a.txt").write_text("A")
        (self.cwd / "b.txt").write_text("B")
        editor = self.root / "swap-editor"
        editor.write_text(
            "#!/usr/bin/env python3\n"
            "import pathlib, sys\n"
            "p = pathlib.Path(sys.argv[-1])\n"
            "s = p.read_text().replace('[1]\ta.txt', "
            "'[1]\tb.txt')\n"
            "s = s.replace('[2]\tb.txt', '[2]\ta.txt')\n"
            "p.write_text(s)\n"
        )
        editor.chmod(0o755)
        self.env["EDITOR"] = str(editor)
        self.backend(
            "ipre_action_wdired",
            "a.txt",
            "b.txt",
            script='source "$1" "$2" "$3" "$4"',
            tty=True,
        )
        self.assertEqual((self.cwd / "a.txt").read_text(), "B")
        self.assertEqual((self.cwd / "b.txt").read_text(), "A")

    def test_batch_rename_rolls_back_when_a_move_fails(self):
        (self.cwd / "a.txt").write_text("A")
        (self.cwd / "b.txt").write_text("B")
        editor = self.root / "rename-editor"
        editor.write_text(
            "#!/usr/bin/env python3\n"
            "import pathlib, sys\n"
            "p = pathlib.Path(sys.argv[-1])\n"
            "s = p.read_text().replace('[1]\ta.txt', "
            "'[1]\ta_new.txt')\n"
            "s = s.replace('[2]\tb.txt', '[2]\tb_new.txt')\n"
            "p.write_text(s)\n"
        )
        editor.chmod(0o755)
        self.env["EDITOR"] = str(editor)
        self.env["IPRE_TEST_FAIL_TARGET"] = str(self.cwd / "b_new.txt")
        self.backend(
            "ipre_action_wdired",
            "a.txt",
            "b.txt",
            script=(
                'read() { return 0; }; '
                'mv() { '
                'if [[ "${@[-1]}" == "$IPRE_TEST_FAIL_TARGET" ]]; '
                'then return 1; fi; command mv "$@"; '
                '}; source "$1" "$2" "$3" "$4"'
            ),
            tty=True,
            expected_returncode=1,
        )
        self.assertEqual((self.cwd / "a.txt").read_text(), "A")
        self.assertEqual((self.cwd / "b.txt").read_text(), "B")
        self.assertEqual({p.name for p in self.cwd.iterdir()}, {"a.txt", "b.txt"})
        self.assertFalse((self.state / "FOCUS").exists())

    def test_rename_absolute_source_and_nested_target_use_source_parent(self):
        folder = self.root / "elsewhere"
        folder.mkdir()
        source = folder / "victim.txt"
        source.write_text("selected")
        (self.cwd / "victim.txt").write_text("root")
        self.rename_item(source, "nested/new.txt")
        target = folder / "nested/new.txt"
        self.assertEqual(target.read_text(), "selected")
        self.assertFalse(source.exists())
        self.assertEqual((self.cwd / "victim.txt").read_text(), "root")
        self.assertEqual((self.state / "FOCUS").read_text(), path_key(target) + "\n")

    def test_rename_dangling_symlink_uses_selected_path(self):
        folder = self.cwd / "sub"
        folder.mkdir()
        source = folder / "link"
        source.symlink_to("missing")
        (self.cwd / "link").write_text("root")
        self.rename_item("sub/link", "renamed-link")
        target = folder / "renamed-link"
        self.assertTrue(target.is_symlink())
        self.assertEqual(os.readlink(target), "missing")
        self.assertFalse(source.is_symlink())
        self.assertEqual((self.cwd / "link").read_text(), "root")

    def test_rename_conflict_is_checked_in_selected_parent(self):
        folder = self.cwd / "sub"
        folder.mkdir()
        source = folder / "victim.txt"
        source.write_text("selected")
        target = folder / "taken.txt"
        target.symlink_to("missing")
        (self.cwd / "victim.txt").write_text("root")
        self.rename_item("sub/victim.txt", "taken.txt", expected_returncode=1)
        self.assertEqual(source.read_text(), "selected")
        self.assertTrue(target.is_symlink())
        self.assertEqual(os.readlink(target), "missing")
        self.assertEqual((self.cwd / "victim.txt").read_text(), "root")
        self.assertFalse((self.state / "FOCUS").exists())

    def test_batch_rename_same_names_resolve_to_distinct_parents(self):
        for name in ("a", "b"):
            folder = self.cwd / name
            folder.mkdir()
            (folder / "same.txt").write_text(name)
        (self.cwd / "same.txt").write_text("root")
        self.batch_rename(
            ["a/same.txt", "b/same.txt"], {1: "renamed.txt", 2: "renamed.txt"}
        )
        for name in ("a", "b"):
            self.assertEqual((self.cwd / name / "renamed.txt").read_text(), name)
            self.assertFalse((self.cwd / name / "same.txt").exists())
            self.assertEqual(list((self.cwd / name).glob(".ipre-rename.*")), [])
        self.assertEqual((self.cwd / "same.txt").read_text(), "root")
        self.assertEqual((self.state / "FOCUS").read_text(), path_key(self.cwd / "a/renamed.txt") + "\n")

    def test_batch_rename_arrow_names_keep_the_selected_identity(self):
        folder = self.cwd / "space folder"
        folder.mkdir()
        source = folder / "a -> b.txt"
        source.write_text("selected")
        (self.cwd / source.name).write_text("root")
        self.batch_rename(["space folder/a -> b.txt"], {1: "c -> d.txt"})
        self.assertEqual((folder / "c -> d.txt").read_text(), "selected")
        self.assertEqual((self.cwd / source.name).read_text(), "root")
        self.assertFalse(source.exists())

    def test_batch_rename_modified_identifier_is_rejected(self):
        folder = self.cwd / "sub"
        folder.mkdir()
        source = folder / "victim.txt"
        source.write_text("selected")
        (self.cwd / "victim.txt").write_text("root")
        editor = self.root / "invalid-editor"
        editor.write_text(
            "#!/usr/bin/env python3\n"
            "import pathlib, sys\n"
            "p = pathlib.Path(sys.argv[-1])\n"
            "p.write_text(p.read_text().replace('[1]\tvictim.txt', "
            "'[9]\trenamed.txt'))\n"
        )
        editor.chmod(0o755)
        self.env["EDITOR"] = str(editor)
        self.backend(
            "ipre_action_wdired", "sub/victim.txt",
            script='read() { return 0; }; source "$1" "$2" "$3"',
            tty=True, expected_returncode=1,
        )
        self.assertEqual(source.read_text(), "selected")
        self.assertEqual((self.cwd / "victim.txt").read_text(), "root")
        self.assertFalse((self.cwd / "renamed.txt").exists())
        self.assertFalse((self.state / "FOCUS").exists())

    def test_batch_rename_stage_failure_rolls_back_in_source_parents(self):
        for name in ("a", "b"):
            folder = self.cwd / name
            folder.mkdir()
            (folder / "same.txt").write_text(name)
        self.env["IPRE_TEST_FAIL_SOURCE"] = str(self.cwd / "b/same.txt")
        self.batch_rename(
            ["a/same.txt", "b/same.txt"], {1: "new.txt", 2: "new.txt"},
            script='mv() { if [[ "${@[-2]}" == "$IPRE_TEST_FAIL_SOURCE" ]]; '
            'then return 1; fi; command mv "$@"; }; ',
            expected_returncode=1,
        )
        for name in ("a", "b"):
            self.assertEqual((self.cwd / name / "same.txt").read_text(), name)
            self.assertEqual({p.name for p in (self.cwd / name).iterdir()}, {"same.txt"})
        self.assertFalse((self.state / "FOCUS").exists())

    def test_batch_rename_long_name_can_be_staged_without_changing_contents(self):
        name = "a" * 255
        (self.cwd / name).write_text("payload")
        self.batch_rename([name], {1: "new.txt"})
        self.assertEqual((self.cwd / "new.txt").read_text(), "payload")
        self.assertEqual({p.name for p in self.cwd.iterdir()}, {"new.txt"})

    def test_batch_rename_overlapping_paths_leave_all_sources_in_place(self):
        folder = self.cwd / "sub"
        folder.mkdir()
        (folder / "victim.txt").write_text("selected")
        self.batch_rename(
            ["sub", "sub/victim.txt"], {1: "renamed-sub", 2: "new.txt"},
            expected_returncode=1,
        )
        self.assertEqual((folder / "victim.txt").read_text(), "selected")
        self.assertEqual({p.name for p in self.cwd.iterdir()}, {"sub"})
        self.assertEqual({p.name for p in folder.iterdir()}, {"victim.txt"})
