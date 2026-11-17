"""Runs the AiDW tests in parallel: one process per test, a few at a time.

Each test already works in its own temporary folder, so they do not share state. Most of the time is spent in `git`
and in the `aidw.py` processes the tests start, which wait on the disk, not on the CPU: running them side by side cuts
the suite from minutes to under one.

    python tests/run.py                      # every test
    python tests/run.py WorktreeTest         # the tests of one class (or several names, or Class.test_name)
    python tests/run.py -j 4                 # at most 4 at a time (default: the number of CPUs, up to 8)

`python -m unittest discover -s tests` still runs them one after the other; `python tests/test_apply.py --update`
still rewrites the reference files.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

TESTS = Path(__file__).resolve().parent


def test_ids(filters: list[str]) -> list[str]:
    def walk(suite):
        for item in suite:
            if isinstance(item, unittest.TestSuite):
                yield from walk(item)
            else:
                yield item.id()

    ids = list(walk(unittest.defaultTestLoader.discover(str(TESTS))))
    if filters:
        ids = [i for i in ids if any(f"{f}." in f"{i}." for f in filters)]
    return ids


def run_one(test_id: str) -> tuple[str, int, float, str]:
    start = time.perf_counter()
    proc = subprocess.run([sys.executable, "-m", "unittest", test_id], cwd=TESTS, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return test_id, proc.returncode, time.perf_counter() - start, proc.stdout + proc.stderr


def main() -> int:
    parser = argparse.ArgumentParser(description="Runs the AiDW tests in parallel.")
    parser.add_argument("names", nargs="*", help="class or Class.test_name to run (default: all)")
    parser.add_argument("-j", "--jobs", type=int, default=min(os.cpu_count() or 4, 8), help="tests at a time")
    args = parser.parse_args()

    ids = test_ids(args.names)
    if not ids:
        print("No test matches.")
        return 1
    start = time.perf_counter()
    failed: list[tuple[str, str]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for future in as_completed([pool.submit(run_one, i) for i in ids]):
            test_id, code, seconds, output = future.result()
            short = test_id.split(".", 1)[-1]
            print(f"  {'ok  ' if code == 0 else 'FAIL'} {seconds:5.1f}s  {short}", flush=True)
            if code != 0:
                failed.append((short, output))
    for short, output in failed:
        print(f"\n===== {short} =====\n{output.strip()}")
    total = time.perf_counter() - start
    print(f"\n{len(ids)} tests in {total:.0f}s: " + (f"{len(failed)} FAILED" if failed else "OK"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
