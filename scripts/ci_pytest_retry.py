#!/usr/bin/env python3
"""Run pytest once, rerun only failed tests once, and emit flaky report."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def _read_lastfailed(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    failed = [nodeid for nodeid, is_failed in data.items() if is_failed]
    failed.sort()
    return failed


def _run(cmd: list[str]) -> int:
    proc = subprocess.run(cmd, check=False)
    return proc.returncode


def _with_prefix(cmd: list[str], xvfb: bool) -> list[str]:
    if xvfb:
        return ["xvfb-run", "-a", *cmd]
    return cmd


def _write_report(
    report_path: Path,
    first_failed: list[str],
    rerun_failed: list[str],
    first_rc: int,
    rerun_rc: int,
) -> None:
    flaky = sorted(set(first_failed) - set(rerun_failed))
    deterministic = sorted(set(rerun_failed))

    lines = [
        "# CI flaky-test report",
        f"first_run_exit_code: {first_rc}",
        f"rerun_exit_code: {rerun_rc}",
        "",
        f"first_run_failed_count: {len(first_failed)}",
        f"deterministic_failed_count: {len(deterministic)}",
        f"flaky_candidate_count: {len(flaky)}",
        "",
        "## deterministic_failures",
    ]
    lines.extend(deterministic or ["- none"])
    lines.extend(["", "## flaky_candidates"])
    lines.extend(flaky or ["- none"])
    lines.extend(["", "## first_run_failures"])
    lines.extend(first_failed or ["- none"])
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xvfb", action="store_true", help="run pytest under xvfb-run -a")
    parser.add_argument(
        "--report",
        default=".ci-flaky-report.txt",
        help="output path for flaky report",
    )
    args = parser.parse_args()

    report_path = Path(args.report)
    lastfailed_path = Path(".pytest_cache") / "v" / "cache" / "lastfailed"

    first_cmd = _with_prefix(["pytest", "tests/", "-v"], args.xvfb)
    first_rc = _run(first_cmd)

    if first_rc == 0:
        _write_report(report_path, [], [], 0, 0)
        return 0

    first_failed = _read_lastfailed(lastfailed_path)
    if not first_failed:
        _write_report(report_path, [], [], first_rc, first_rc)
        return first_rc

    rerun_cmd = _with_prefix(
        ["pytest", "--last-failed", "--last-failed-no-failures", "none", "-v"],
        args.xvfb,
    )
    rerun_rc = _run(rerun_cmd)

    rerun_failed = _read_lastfailed(lastfailed_path) if rerun_rc != 0 else []
    _write_report(report_path, first_failed, rerun_failed, first_rc, rerun_rc)

    return 1 if rerun_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
