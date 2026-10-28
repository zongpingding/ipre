"""Run the real pre entry point; replace only PDF rendering and display tools."""

import json
import os
import pathlib
import subprocess

from support import IpreTestCase, ROOT


class CacheTests(IpreTestCase):
    def setUp(self):
        super().setUp()
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        scripts = {
            "pdfinfo": 'print("Pages: 10")\n',
            "pdftoppm": (
                'source = pathlib.Path(sys.argv[-2])\n'
                'page = sys.argv[sys.argv.index("-f") + 1]\n'
                'pathlib.Path(sys.argv[-1] + ".png").write_bytes(page.encode() + b":" + source.read_bytes())\n'
                'with open(os.environ["IPRE_TEST_GENERATIONS"], "a") as log: log.write("generated\\n")\n'
            ),
            "chafa": (
                'image = pathlib.Path(sys.argv[-1])\n'
                'pathlib.Path(os.environ["IPRE_TEST_IMAGE"]).write_text(json.dumps(str(image)))\n'
                'sys.stdout.buffer.write(image.read_bytes())\n'
            ),
        }
        for name, body in scripts.items():
            command = bin_dir / name
            command.write_text('#!/usr/bin/env python3\nimport json,os,pathlib,sys\n' + body)
            command.chmod(0o755)
        self.env.update(PATH=f"{bin_dir}:{self.env['PATH']}",
                        IPRE_TEST_GENERATIONS=str(self.root / "generations"),
                        IPRE_TEST_IMAGE=str(self.root / "image"))

    def preview(self, source, cwd, page=1):
        result = subprocess.run([str(ROOT / "pre"), str(source), f"PAGE:{page}"],
                                cwd=cwd, env=self.env, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        image = pathlib.Path(json.loads((self.root / "image").read_text()))
        self.assertEqual(image.parent, pathlib.Path(self.env["XDG_CACHE_HOME"]) / "pre_thumbs")
        return image, result.stdout

    def test_same_name_and_timestamp_in_different_directories_have_distinct_previews(self):
        images = []
        for name, content in (("one", b"FIRST"), ("two", b"OTHER")):
            folder = self.root / name
            folder.mkdir()
            source = folder / "doc.pdf"
            source.write_bytes(content)
            os.utime(source, ns=(1700000000000000000,) * 2)
            image, output = self.preview("doc.pdf", folder)
            self.assertEqual(output, b"1:" + content)
            images.append(image)
        self.assertNotEqual(*images)

    def test_relative_absolute_and_special_paths_reuse_the_same_cache(self):
        source = self.cwd / "a -> %09\t'quoted'\n.pdf"
        source.write_bytes(b"FIRST")
        first, output = self.preview(source.name, self.cwd)
        second, repeated = self.preview(source, self.root)
        self.assertEqual(first, second)
        self.assertEqual(output, repeated)
        self.assertEqual((self.root / "generations").read_text(), "generated\n")

    def test_same_second_edits_and_restored_mtime_invalidate_cache(self):
        source = self.cwd / "doc.pdf"
        stamp = 1700000000000000000
        images = []
        for content, ns in ((b"FIRST", stamp + 100000), (b"OTHER", stamp + 900000),
                            (b"THIRD", stamp + 900000)):
            source.write_bytes(content)
            os.utime(source, ns=(ns, ns))
            image, output = self.preview(source, self.cwd)
            self.assertEqual(output, b"1:" + content)
            images.append(image)
        self.assertEqual(len(set(images)), 3)

    def test_page_number_is_part_of_cache_identity(self):
        source = self.cwd / "doc.pdf"
        source.write_bytes(b"FIRST")
        first, output = self.preview(source, self.cwd, page=1)
        second, other = self.preview(source, self.cwd, page=2)
        self.assertNotEqual(first, second)
        self.assertEqual(output, b"1:FIRST")
        self.assertEqual(other, b"2:FIRST")
