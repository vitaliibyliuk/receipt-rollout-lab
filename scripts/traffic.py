import argparse
import csv
import json
from math import ceil
from pathlib import Path
from time import perf_counter, sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ATTEMPTS = 200
TIMEOUT = 2.0
INTERVAL = 0.025
P95_LIMIT = 200
SLO = 99
URLS = {"v1": "http://127.0.0.1:8181", "v2": "http://127.0.0.1:8182"}
COLUMNS = ("attempt", "version", "submission_key", "status", "latency_ms", "request_id", "submission_id", "exception")


def send(version, key, number):
    payload = json.dumps({"group_code": "SE-42", "submission_key": key}).encode()
    request = Request(
        URLS[version] + "/submissions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    row = dict.fromkeys(COLUMNS, "")
    row.update(attempt=number, version=version, submission_key=key)
    started = perf_counter()
    try:
        try:
            response = urlopen(request, timeout=TIMEOUT)
        except HTTPError as error:
            response = error
        with response:
            row["status"] = response.code
            row["request_id"] = response.headers.get("X-Request-Id", "")
            raw = response.read()
    except (TimeoutError, URLError, OSError) as error:
        row.update(status="", exception=type(error).__name__)
    finally:
        row["latency_ms"] = round((perf_counter() - started) * 1000, 6)
    if row["status"]:
        try:
            document = json.loads(raw)
            if isinstance(document, dict):
                row["submission_id"] = document.get("id", "")
        except (ValueError, UnicodeDecodeError):
            pass
    return row


def summarize(rows):
    count = len(rows)
    responses = sorted(r["latency_ms"] for r in rows if r["status"])
    five = sum(isinstance(r["status"], int) and 500 <= r["status"] < 600 for r in rows)
    unanswered = count - len(responses)
    return {
        "attempts": count,
        "http_5xx": five,
        "no_response": unanswered,
        "error_percent": round(100 * (five + unanswered) / count, 3) if count else None,
        "p95_ms": responses[ceil(0.95 * len(responses)) - 1] if responses else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("baseline", "canary", "rollback"))
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    with (args.output / f"{args.phase}.csv").open("x", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=COLUMNS)
        writer.writeheader()
        for n in range(1, ATTEMPTS + 1):
            version = "v2" if args.phase == "canary" and n % 10 == 0 else "v1"
            row = send(version, f"{args.prefix}-{args.phase}-{n:03d}", n)
            writer.writerow(row)
            rows.append(row)
            sleep(INTERVAL)
    good = sum(r["status"] == 201 and r["latency_ms"] <= 1000 for r in rows)
    summary = {
        "phase": args.phase,
        "slo_percent": SLO,
        "sli_percent": round(100 * good / ATTEMPTS, 3),
        "sli_numerator": good,
        "attempts": ATTEMPTS,
        "p95_limit_ms": P95_LIMIT,
        "versions": {v: summarize([r for r in rows if r["version"] == v]) for v in URLS},
    }
    if args.phase == "canary":
        candidate = summary["versions"]["v2"]
        summary["expand_allowed"] = (
            candidate["attempts"] >= 20
            and candidate["error_percent"] <= 5
            and candidate["p95_ms"] is not None
            and candidate["p95_ms"] <= P95_LIMIT
        )
    (args.output / f"{args.phase}-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{args.phase} | SLI {good}/{ATTEMPTS} = {summary['sli_percent']:.2f}% | SLO {SLO}%")
    print("VERSION  TRIES  5XX  NO REPLY  ERRORS %  P95 ms")
    for version, s in summary["versions"].items():
        error = "-" if s["error_percent"] is None else f"{s['error_percent']:.2f}"
        p95 = "-" if s["p95_ms"] is None else f"{s['p95_ms']:.2f}"
        print(f"{version:<8} {s['attempts']:>5} {s['http_5xx']:>4} {s['no_response']:>9} {error:>9} {p95:>7}")
    if "expand_allowed" in summary:
        action = "EXPAND" if summary["expand_allowed"] else "ROLL BACK"
        print(f"CANDIDATE VERDICT: {action}")


if __name__ == "__main__":
    main()
