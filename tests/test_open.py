"""Opening uses pre's type API and preserves argv across mixed selections."""

import base64
import json
import os
import shlex
import subprocess
import time
import wave

from support import IpreTestCase, ROOT, path_key


class OpenTests(IpreTestCase):
    def setUp(self):
        super().setUp()
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.log = self.root / "open-log"
        self.env["IPRE_TEST_OPEN_LOG"] = str(self.log)
        for name in ("editor", "image", "document", "media", "system", "custom tool"):
            command = self.bin_dir / name
            command.write_text(
                '#!/usr/bin/env python3\nimport json,os,pathlib,sys\n'
                'with open(os.environ["IPRE_TEST_OPEN_LOG"], "a") as out:\n'
                '    out.write(json.dumps([pathlib.Path(sys.argv[0]).name, sys.argv[1:]]) + "\\n")\n'
            )
            command.chmod(0o755)
        self.env.update(PATH=f"{self.bin_dir}:{self.env['PATH']}", EDITOR="editor --wait",
                        IPRE_IMAGE_OPENER="image", IPRE_DOCUMENT_OPENER="document",
                        IPRE_MEDIA_OPENER="media", IPRE_SYSTEM_OPENER="system")

    def calls(self, count):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                calls = [json.loads(line) for line in self.log.read_text().splitlines()]
            except (FileNotFoundError, ValueError):
                calls = []
            if len(calls) >= count:
                return calls
            time.sleep(0.01)
        self.fail(f"expected {count} opener calls, got {calls}")

    def test_mixed_selection_uses_pre_api_and_groups_each_type(self):
        kinds = ["text", "image", "pdf", "text", "image", "djvu", "audio", "binary"]
        files = [self.cwd / f"item{i} -> %0A\n.odd" for i in range(len(kinds))]
        for file in files:
            file.write_text("payload")
        self.env["IPRE_TEST_TYPES"] = json.dumps({str(file): kind for file, kind in zip(files, kinds)})
        mock_pre = self.bin_dir / "pre"
        mock_pre.write_text(
            '#!/usr/bin/env python3\nimport json,os,sys\n'
            'assert sys.argv[1] == "get_file_type"\n'
            'print(json.loads(os.environ["IPRE_TEST_TYPES"])[sys.argv[2]])\n'
        )
        mock_pre.chmod(0o755)
        result = self.backend("ipre_action_open", "--encoded", *(path_key(p) for p in files))
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls(6)
        self.assertIn(["editor", ["--wait", str(files[0]), str(files[3])]], calls)
        self.assertIn(["image", [str(files[1]), str(files[4])]], calls)
        self.assertIn(["document", [str(files[2])]], calls)
        self.assertIn(["document", [str(files[5])]], calls)
        self.assertIn(["media", [str(files[6])]], calls)
        self.assertIn(["system", [str(files[7])]], calls)

    def test_real_pre_detects_extensionless_documents_images_and_audio(self):
        pdf = self.cwd / "document"
        pdf.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n")
        png = self.cwd / "picture"
        png.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="))
        audio = self.cwd / "sound"
        with wave.open(str(audio), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(b"\0\0" * 80)
        note = self.cwd / "notes"
        note.write_text("plain text\n")
        result = self.backend("ipre_action_open", *(str(p) for p in (pdf, png, audio, note)))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertCountEqual(self.calls(4), [
            ["document", [str(pdf)]], ["image", [str(png)]],
            ["media", [str(audio)]], ["editor", ["--wait", str(note)]],
        ])

    def test_open_with_editor_overrides_detected_type_and_keeps_paths_literal(self):
        source = self.cwd / "a ' ; $(touch marker) ->\n.pdf"
        source.write_text("payload")
        result = self.backend(
            "ipre_action_probe", str(source),
            script='ipre_action_probe() { :; }; fzf() { printf "editor\\tText editor\\n"; }; '
            'source "$1" "$2"; ipre_palette_do_open_with "${@:3}"', tty=True,
        )
        self.assert_ui_is_scoped(result)
        self.assertEqual(self.calls(1), [["editor", ["--wait", str(source)]]])
        self.assertFalse((self.cwd / "marker").exists())

    def test_custom_opener_tokenizes_options_without_shell_expansion(self):
        source = self.cwd / "spaces and\nnewlines"
        source.write_text("payload")
        self.env["IPRE_TEST_OPEN_SPEC"] = shlex.quote(str(self.bin_dir / "custom tool")) + " --label 'two words' '$USER'"
        self.backend(
            "ipre_action_probe", str(source),
            script='ipre_action_probe() { :; }; source "$1" "$2"; '
            'ipre_open_command foreground "$IPRE_TEST_OPEN_SPEC" "${@:3}"',
        )
        self.assertEqual(self.calls(1), [["custom tool", ["--label", "two words", "$USER", str(source)]]])

    def test_open_with_cancel_leaves_screen_and_launches_nothing(self):
        source = self.cwd / "source.txt"
        source.write_text("payload")
        result = self.backend(
            "ipre_action_probe", str(source),
            script='ipre_action_probe() { :; }; fzf() { return 130; }; '
            'source "$1" "$2"; ipre_palette_do_open_with "${@:3}"', tty=True,
        )
        self.assert_ui_is_scoped(result)
        self.assertFalse(self.log.exists())

    def test_missing_opener_reports_failure_without_using_another_type(self):
        source = self.cwd / "source.txt"
        source.write_text("payload")
        self.env["EDITOR"] = "ipre-nonexistent-test-editor"
        result = self.backend("ipre_action_open", str(source))
        self.assertEqual(result.returncode, 1)
        self.assertIn("program unavailable", (self.state / "NOTICE").read_text())
        self.assertFalse(self.log.exists())

    def test_main_exit_and_keep_open_use_the_same_type_dispatch(self):
        source = self.cwd / "document"
        source.write_bytes(b"%PDF-1.4\n%%EOF\n")
        fzf = self.bin_dir / "fzf"
        fzf.write_text(
            '#!/usr/bin/env python3\nimport os,subprocess,sys\n'
            'record = next(line for line in sys.stdin if "document" in line)\n'
            'if os.environ.get("IPRE_TEST_KEEP_OPEN"):\n'
            '    binding = next(arg for arg in sys.argv if arg.startswith("enter:execute("))\n'
            '    assert "ipre_action_open --encoded {+1}" in binding\n'
            '    subprocess.run([os.environ["IPRE_BACKEND_CMD"], "ipre_action_open", "--encoded", record.split("\\t")[0]], check=True)\n'
            'else: sys.stdout.write(record)\n'
        )
        fzf.chmod(0o755)
        for keep in (False, True):
            env = dict(self.env)
            if keep:
                env["IPRE_TEST_KEEP_OPEN"] = "1"
            result = subprocess.run([str(ROOT / "ipre"), str(self.cwd), *( ["--keep-open"] if keep else [])],
                                    env=env, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(2), [["document", [str(source)]], ["document", [str(source)]]])
