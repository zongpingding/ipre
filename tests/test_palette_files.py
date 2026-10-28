"""Palette links, content copying and ipre's own command history."""

import json
import os
import shlex

from support import IpreTestCase, editor_text, path_key


class PaletteFileTests(IpreTestCase):
    def setUp(self):
        super().setUp()
        self.history = self.root / "commands.history-v1"
        self.env["IPRE_COMMAND_HISTORY_FILE"] = str(self.history)

    def test_symlink_palette_preserves_targets_and_refuses_existing_paths(self):
        source = self.cwd / "target %\nfile"
        source.write_text("original")
        destination = self.cwd / "nested" / "link\tname"
        self.env["IPRE_TEST_LINK"] = editor_text(destination)
        script = ('fzf() { print -r -- "symlink | Create symbolic links"; }; '
                  'vared() { link_name="$IPRE_TEST_LINK"; }; read() { :; }; '
                  'source "$1" "${@:2}"')
        self.backend("ipre_action_command_palette", "--encoded", path_key(source),
                     script=script, tty=True)
        self.assertEqual(os.readlink(destination), str(source))
        self.assertEqual((self.state / "FOCUS").read_text().strip(), path_key(destination))
        other = self.cwd / "other"
        other.write_text("other")
        self.backend("ipre_action_command_palette", "--encoded", path_key(other),
                     script=script, tty=True, expected_returncode=1)
        self.assertEqual(os.readlink(destination), str(source))
        self.assertEqual(source.read_text(), "original")

    def test_symlink_cancel_restores_screen_without_creating_a_link(self):
        source = self.cwd / "source"
        source.write_text("original")
        self.backend("ipre_action_command_palette", source,
                     script='fzf() { print "symlink | Links"; }; vared() { return 1; }; '
                            'read() { :; }; source "$1" "${@:2}"', tty=True)
        self.assertEqual(list(self.cwd.iterdir()), [source])

    def test_content_palette_copies_exact_bytes_and_validates_all_inputs(self):
        source = self.cwd / "one\nfile"
        other = self.cwd / "two file"
        source.write_bytes(b"first\x00\xff\n\n")
        other.write_bytes(b"second\n\n")
        copied = self.root / "clipboard"
        copier = self.root / "clipboard program"
        copier.write_text('#!/usr/bin/env python3\nimport pathlib,sys\n'
                          'pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())\n')
        copier.chmod(0o755)
        self.env["CLIPBOARD"] = f'{shlex.quote(str(copier))} {shlex.quote(str(copied))}'
        script = 'fzf() { print "content | Copy contents"; }; source "$1" "${@:2}"'
        self.backend("ipre_action_command_palette", source, other, script=script, tty=True)
        self.assertEqual(copied.read_bytes(), source.read_bytes() + other.read_bytes())
        self.backend("ipre_action_command_palette", source, self.cwd, script=script,
                     tty=True, expected_returncode=1)
        self.assertEqual(copied.read_bytes(), source.read_bytes() + other.read_bytes())
        self.assertIn("not a readable file", (self.state / "NOTICE").read_text())

    def test_shell_command_history_records_execution_but_not_cancel(self):
        for mode in ("b", "n", "invalid"):
            self.backend(
                "ipre_action_probe", tty=True,
                script='ipre_action_probe() { :; }; vared() { cmd_str="true"; }; '
                       f'read() {{ mode={mode}; }}; sleep() {{ :; }}; '
                       'source "$1" "$2"; ipre_palette_do_shell_cmd',
            )
        self.assertEqual(self.history.read_text().splitlines(), ["true", "true"])
        self.assertEqual(self.history.stat().st_mode & 0o777, 0o600)

    def test_history_palette_applies_all_or_each_and_keeps_paths_as_arguments(self):
        log = self.root / "arguments"
        recorder = self.root / "record args"
        recorder.write_text('#!/usr/bin/env python3\nimport json,os,sys\n'
                            'with open(os.environ["IPRE_TEST_LOG"],"a") as f:\n'
                            '    f.write(json.dumps(sys.argv[1:])+"\\n")\n')
        recorder.chmod(0o755)
        self.env["IPRE_TEST_LOG"] = str(log)
        command = shlex.quote(str(recorder))
        # Duplicates and multiline commands round-trip without becoming records.
        self.history.write_text(editor_text("false\nprintf ignored") + "\n"
                                + editor_text(command) + "\n" + editor_text(command) + "\n")
        first = self.cwd / 'literal $(touch INJECTED) "file"\n'
        second = self.cwd / "second;file"
        first.touch()
        second.touch()
        for mode in ("all", "each"):
            self.env["IPRE_TEST_MODE"] = mode
            self.backend(
                "ipre_action_command_palette", "--encoded", path_key(first), path_key(second),
                tty=True, script='fzf() { case "$*" in '
                '*"Command > "*) print "history | Command history" ;; '
                '*"Command history > "*) cat > "$IPRE_TEST_LOG.choices"; '
                'head -n 1 "$IPRE_TEST_LOG.choices" ;; '
                '*) print -r -- "$IPRE_TEST_MODE" ;; esac; }; '
                'vared() { :; }; read() { :; }; source "$1" "${@:2}"',
            )
        invocations = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(invocations, [[str(first), str(second)], [str(first)], [str(second)]])
        self.assertFalse((self.cwd / "INJECTED").exists())
        # Reusing the edited template must not append a second "$@".
        self.assertEqual(self.history.read_text().splitlines()[-1], editor_text(command + ' "$@"'))

    def test_history_cancel_does_not_execute_or_record(self):
        self.history.write_text("touch SHOULD_NOT_EXIST\n")
        self.backend(
            "ipre_action_probe", tty=True,
            script='ipre_action_probe() { :; }; fzf() { return 130; }; '
                   'source "$1" "$2"; ipre_palette_do_history_cmd "$IPRE_CWD"',
        )
        self.assertFalse((self.cwd / "SHOULD_NOT_EXIST").exists())
        self.assertEqual(self.history.read_text(), "touch SHOULD_NOT_EXIST\n")
