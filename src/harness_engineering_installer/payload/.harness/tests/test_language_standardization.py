#!/usr/bin/env python3

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_ROOT = REPO_ROOT / ".harness"
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SKIP_DIRS = {"__pycache__"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def find_han_matches(root: Path) -> list[str]:
    matches: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if SKIP_DIRS.intersection(path.relative_to(root).parts):
            continue
        if path.suffix in SKIP_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(root).as_posix()
        for line_no, line in enumerate(text.splitlines(), start=1):
            if HAN_RE.search(line):
                matches.append(f"{rel}:{line_no}")
    return matches


class LanguageStandardizationTest(unittest.TestCase):
    def test_harness_assets_do_not_contain_han_text(self) -> None:
        matches = find_han_matches(HARNESS_ROOT)

        self.assertEqual([], matches, "\n".join(matches))

    def test_scanner_catches_accidental_han_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "scripts" / "example.py"
            target.parent.mkdir(parents=True)
            han_text = "\u4e2d\u6587"
            target.write_text(f"print('{han_text}')\n", encoding="utf-8")

            matches = find_han_matches(root)

        self.assertEqual(["scripts/example.py:1"], matches)


if __name__ == "__main__":
    unittest.main()
