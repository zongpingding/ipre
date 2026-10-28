"""Command prompt exits must always restore the browser's screen."""

import re
import shutil

from support import IpreTestCase, editor_text


class PaletteTests(IpreTestCase):
    def command_with_raw_output(self, action, responses, flags="-opost -onlcr"):
        before = self.root / "tty-before"
        after = self.root / "tty-after"
        self.env["IPRE_TEST_TTY_BEFORE"] = str(before)
        self.env["IPRE_TEST_TTY_AFTER"] = str(after)
        self.env["IPRE_TEST_TTY_SCRIPT"] = (
            'ipre_action_probe() { :; }; source "$1" "$2"; '
            'stty -g </dev/tty > "$IPRE_TEST_TTY_BEFORE"; '
            + action + '; result=$?; '
            'stty -g </dev/tty > "$IPRE_TEST_TTY_AFTER"; exit "$result"'
        )
        # Start zsh with these settings too, so ZLE sees the inherited raw mode.
        result = self.backend(
            "ipre_action_probe", tty=True, responses=responses,
            script=f'stty {flags} </dev/tty; '
                   'exec zsh -f -c "$IPRE_TEST_TTY_SCRIPT" - "$1" "$2"',
        )
        self.assertEqual(after.read_bytes(), before.read_bytes())
        return result.stdout

    def test_real_shell_prompt_and_output_restore_newline_processing(self):
        (self.cwd / "LS_ROW1").touch()
        (self.cwd / "LS_ROW2").touch()
        for flags in ("-opost onlcr", "opost -onlcr"):
            with self.subTest(flags=flags):
                output = self.command_with_raw_output(
                    'ipre_palette_do_shell_cmd', flags=flags,
                    responses=((b"Enter command:", b"printf 'ROW1\\nROW2\\n'; ls -1 -- LS_ROW1 LS_ROW2\r"),
                               (b"Choice:", b"b"), (b"Press any key", b"x")),
                )
                output = re.sub(r"\x1b\[[0-9;]*m", "", output)
                menu = output.split("Select execution mode:", 1)[1].split("Choice:", 1)[0]
                self.assertNotRegex(menu, r"(?<!\r)\n")
                self.assertIn("ROW1\r\nROW2\r\n", output)
                self.assertIn("LS_ROW1\r\nLS_ROW2\r\n", output)

    def test_real_history_pickers_and_command_output_restore_newline_processing(self):
        if not shutil.which("fzf"):
            self.skipTest("fzf is required for the history picker")
        history = self.root / "command-history"
        history.write_text(editor_text('printf \'%s\\n\' "$@"') + "\n")
        self.env["IPRE_COMMAND_HISTORY_FILE"] = str(history)
        for mode in (b"All selected", b"One invocation"):
            with self.subTest(mode=mode):
                output = self.command_with_raw_output(
                    'ipre_palette_do_history_cmd HISTORY_ROW1 HISTORY_ROW2',
                    responses=((b"Command history >", b"\r"), (b"Command:", b"\r"),
                               (b"Apply command >", mode + b"\r"), (b"Press any key", b"x")),
                )
                self.assertIn("HISTORY_ROW1\r\nHISTORY_ROW2\r\n", output)
                self.assertIn('Place "$@" where the selected paths belong, including within pipelines.\r\n', output)

    def test_cancelled_prompt_restores_inherited_terminal_settings(self):
        output = self.command_with_raw_output(
            'ipre_palette_do_shell_cmd', responses=((b"Enter command:", b"\x03"),),
        )
        self.assertNotIn("Select execution mode", output)

    def test_shell_prompt_real_ctrl_c_restores_screen(self):
        result = self.backend(
            "ipre_action_probe",
            script='ipre_action_probe() { :; }; source "$1" "$2"; ipre_palette_do_shell_cmd',
            tty=True, responses=[(b"Enter command:", b"\x03")],
        )
        self.assertNotIn("Select execution mode", result.stdout)
        self.assert_ui_is_scoped(result)

    def test_shell_prompt_cancel_and_empty_input_restore_screen(self):
        for prompt in ('vared() { return 1; };', 'vared() { cmd_str=""; };'):
            with self.subTest(prompt=prompt):
                result = self.backend(
                    "ipre_action_probe",
                    script='ipre_action_probe() { :; }; ' + prompt +
                    'source "$1" "$2"; ipre_palette_do_shell_cmd', tty=True,
                )
                self.assertNotIn("continue", result.stdout)
                self.assertNotIn("Select execution mode", result.stdout)
                self.assert_ui_is_scoped(result)

    def test_shell_execution_modes_restore_screen(self):
        for mode in ("b", "n", "invalid"):
            with self.subTest(mode=mode):
                result = self.backend(
                    "ipre_action_probe",
                    script='ipre_action_probe() { :; }; vared() { cmd_str="false"; }; '
                    f'read() {{ mode={mode}; }}; sleep() {{ :; }}; '
                    'source "$1" "$2"; ipre_palette_do_shell_cmd', tty=True,
                )
                self.assert_ui_is_scoped(result)
