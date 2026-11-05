"""inbox_archive：收件箱 → 已处理/日/（临时目录，勿碰真图）。"""
from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest

from review_tool.pipeline import inbox_archive as ia


class TestInboxArchive(unittest.TestCase):
    def test_dry_run_keeps_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            inbox = os.path.join(tmp, "收件箱")
            os.makedirs(inbox)
            src = os.path.join(inbox, "shot.jpg")
            with open(src, "wb") as f:
                f.write(b"fake")
            r = ia.archive_inbox_files([src], "2099-05-01", inbox_dir=inbox, write=False)
            self.assertEqual(len(r["planned"]), 1)
            self.assertTrue(os.path.isfile(src))
            self.assertFalse(os.path.isdir(r["dest_dir"]))

    def test_write_moves_into_processed(self):
        with tempfile.TemporaryDirectory() as tmp:
            inbox = os.path.join(tmp, "收件箱")
            os.makedirs(inbox)
            src = os.path.join(inbox, "shot.png")
            with open(src, "wb") as f:
                f.write(b"img")
            r = ia.archive_inbox_files([src], "2099-05-02", inbox_dir=inbox, write=True)
            self.assertEqual(len(r["moved"]), 1)
            self.assertFalse(os.path.isfile(src))
            dest = r["moved"][0]["dest"]
            self.assertTrue(os.path.isfile(dest))
            self.assertIn(os.path.join("已处理", "2099-05-02"), dest)
            with open(dest, "rb") as f:
                self.assertEqual(f.read(), b"img")

    def test_outside_inbox_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            inbox = os.path.join(tmp, "收件箱")
            os.makedirs(inbox)
            outsider = os.path.join(tmp, "other.jpg")
            with open(outsider, "wb") as f:
                f.write(b"x")
            r = ia.archive_inbox_files(
                [outsider], "2099-05-03", inbox_dir=inbox, write=True
            )
            self.assertEqual(r["moved"], [])
            self.assertEqual(r["skipped"][0]["reason"], "outside_inbox")
            self.assertTrue(os.path.isfile(outsider))

    def test_main_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            inbox = os.path.join(tmp, "收件箱")
            os.makedirs(inbox)
            src = os.path.join(inbox, "a.jpg")
            with open(src, "wb") as f:
                f.write(b"a")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = ia.main(
                    ["--date", "2099-05-04", "--file", src, "--inbox", inbox, "--write"]
                )
            self.assertEqual(rc, 0)
            self.assertFalse(os.path.isfile(src))


if __name__ == "__main__":
    unittest.main()
