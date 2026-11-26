"""Run every eval's reference command and check its numbers, so evals/evals.json never drifts."""
import contextlib
import io
import json
import os
import shlex
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import rfcalc  # noqa: E402

EVALS_PATH = os.path.join(ROOT, "evals", "evals.json")


def run_json(cmd):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = rfcalc.main(["--json", *shlex.split(cmd)])
    if code != 0:
        raise AssertionError(f"command failed ({code}): {cmd}")
    return json.loads(buf.getvalue())


def lookup(obj, path):
    for part in path.split("."):
        obj = obj[int(part)] if isinstance(obj, list) else obj[part]
    return obj


class Evals(unittest.TestCase):
    def test_eval_file_matches_skill_name_and_has_unique_ids(self):
        with open(EVALS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["skill_name"], "rf-engineering")
        ids = [e["id"] for e in data["evals"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_reference_commands_produce_expected_values(self):
        with open(EVALS_PATH, encoding="utf-8") as fh:
            evals = json.load(fh)["evals"]
        for ev in evals:
            if "command" not in ev:
                continue
            out = run_json(ev["command"])
            for path, (want, tol) in ev["checks"].items():
                with self.subTest(eval=ev["id"], key=path):
                    got = lookup(out, path)
                    if isinstance(want, bool):
                        self.assertIs(got, want)
                    else:
                        self.assertAlmostEqual(got, want, delta=tol)


if __name__ == "__main__":
    unittest.main()
