"""Regression tests for paths."""

import os
import subprocess

from support import IpreTestCase, ROOT, path_key


class PathsTests(IpreTestCase):
    def test_path_codec_preserves_all_nonzero_bytes_and_rejects_invalid_encoding(self):
        payload = bytes(range(1, 256)) + b"%0A\\n\n"
        result = subprocess.run(
            ["zsh", "-fc",
             'source "$1"; ipre_path_encode "$2"; encoded="$REPLY"; '
             'ipre_path_decode "$encoded" || exit 1; printf "%s" "$REPLY"',
             "-", str(ROOT / "ipre_paths"), os.fsdecode(payload)],
            capture_output=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, payload)
        for text in (payload, "中文\u0085\n\\tail".encode()):
            result = subprocess.run(
                ["zsh", "-fc",
                 'source "$1"; ipre_text_escape "$2"; escaped="$REPLY"; '
                 'ipre_text_unescape "$escaped" || exit 1; printf "%s" "$REPLY"',
                 "-", str(ROOT / "ipre_paths"), os.fsdecode(text)],
                capture_output=True, timeout=5,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, text)
        for malformed in ("%", "%0", "%GG", "%00", "raw\tpath", "raw\npath"):
            with self.subTest(malformed=malformed):
                result = self.backend("ipre_action_copy", "--encoded", malformed)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((self.state / "CLIP").read_text(), "")

    def test_stream_reader_preserves_bytes_across_chunks(self):
        payloads = [b"", b"a" * 65535 + "中文".encode() + b"\n\xff", b"tail\n"]
        wire = b"\0".join(payloads) + b"\0"
        result = subprocess.run(
            ["zsh", "-fc", 'source "$1"; IPRE_INPUT_BUFFER=""; '
             'while ipre_stream_read $\'\\0\'; do printf "%s\\0" "$REPLY"; done',
             "-", str(ROOT / "ipre_paths")],
            input=wire, capture_output=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, wire)

    def test_raw_arguments_do_not_decode_literal_percent_sequences(self):
        literal = self.cwd / "literal%0A"
        literal.write_text("literal")
        (self.cwd / "literal\n").write_text("newline")
        self.backend("ipre_action_copy", literal.name)
        self.assertEqual((self.state / "CLIP").read_text(), f"COPY\n{path_key(literal)}\n")
