"""Preview sizing and layout changes in the real frontend."""

import json
import shutil

from support import IpreTestCase


class PreviewGeometryTests(IpreTestCase):
    def test_size_limits_and_layout_preserve_the_selected_size(self):
        for action, geometry in (("shrink", "right 40"), ("toggle", "down 40"),
                                 ("grow", "down 50"), ("toggle", "right 50")):
            result = self.backend("ipre_action_preview_geometry", action)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((self.state / "preview_geometry").read_text().strip(), geometry)
        for action, limit in (("grow", 80), ("shrink", 20)):
            for _ in range(10):
                self.backend("ipre_action_preview_geometry", action)
            self.assertEqual((self.state / "preview_geometry").read_text().strip(), f"right {limit}")

    def test_real_main_f4_f5_f6_resize_and_reorient_preview(self):
        if not shutil.which("fzf") or not shutil.which("fd"):
            self.skipTest("fzf and fd are required")
        (self.cwd / "example.txt").write_text("preview")
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        preview = bin_dir / "pre"
        preview.write_text(
            '#!/usr/bin/env python3\nimport os,pathlib,json\n'
            'layout,size=pathlib.Path(os.environ["IPRE_RAM_DIR"],"preview_geometry").read_text().split()\n'
            'row=[layout,int(size),int(os.environ["FZF_PREVIEW_COLUMNS"]),int(os.environ["FZF_PREVIEW_LINES"])]\n'
            'with open(os.environ["IPRE_TEST_GEOMETRY_LOG"],"a") as f: f.write(json.dumps(row)+"\\n")\n'
            'print("GEOMETRY_"+layout+"_"+size)\n'
        )
        preview.chmod(0o755)
        log = self.root / "geometry-log"
        self.env["IPRE_TEST_GEOMETRY_LOG"] = str(log)
        self.env["PATH"] = f"{bin_dir}:{self.env['PATH']}"
        self.backend(
            "ipre_action_probe", tty=True,
            script='ipre_action_probe() { :; }; source "$1" "$2"; '
                   'exec "${1:h}/ipre" "$IPRE_CWD" --depth 1',
            responses=((b"GEOMETRY_right_50", b"\x1bOS"),       # F4
                       (b"GEOMETRY_right_40", b"\x1b[17~"),    # F6
                       (b"GEOMETRY_down_40", b"\x1b[15~"),     # F5
                       (b"GEOMETRY_down_50", b"\x11")),
        )
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        by_state = {(row[0], row[1]): row[2:] for row in rows}
        self.assertLess(by_state["right", 40][0], by_state["right", 50][0])
        self.assertGreater(by_state["down", 40][0], by_state["right", 40][0])
        self.assertGreater(by_state["down", 50][1], by_state["down", 40][1])
