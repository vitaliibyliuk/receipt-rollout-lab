import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path


def test_suite(timeout, report):
    command = [sys.executable, "-m", "pytest", "-q", "tests"]
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        command.append(f"--junitxml={report}")
    try:
        return subprocess.run(command, timeout=timeout, check=False).returncode
    except subprocess.TimeoutExpired:
        print(f"Test time limit exceeded ({timeout:g} s)", file=sys.stderr)
        return 124


def summarize(log):
    counts = Counter()
    try:
        with log.open(encoding="utf-8") as records:
            for row in records:
                event = json.loads(row)
                if event["event"] == "submission_response":
                    counts[event["version"], event["status"]] += 1
    except FileNotFoundError:
        print(f"Log file does not exist: {log}", file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError) as error:
        print(f"Cannot read log: {error}", file=sys.stderr)
        return 2
    print("VERSION  STATUS  COUNT")
    for (version, status), count in sorted(counts.items()):
        print(f"{version:<8} {status:<7} {count}")
    return 0


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="action", required=True)
    tests = commands.add_parser("test")
    tests.add_argument("--timeout", type=float, default=60)
    tests.add_argument("--junit", type=Path)
    log = commands.add_parser("summarize")
    log.add_argument("log", type=Path)
    args = parser.parse_args()
    if args.action == "test":
        if args.timeout <= 0:
            parser.error("--timeout must be positive")
        return test_suite(args.timeout, args.junit)
    return summarize(args.log)


if __name__ == "__main__":
    raise SystemExit(main())
