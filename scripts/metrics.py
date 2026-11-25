"""Capture the actual instant query used during the canary."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

QUERY = "sum by (version, status) (submission_responses_total)"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = "http://127.0.0.1:9190/api/v1/query?" + urlencode({"query": QUERY})
    with urlopen(url, timeout=3) as response:
        report = json.load(response)
    if report.get("status") != "success" or report["data"]["resultType"] != "vector":
        raise SystemExit("Prometheus did not return a count vector")
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    rows = sorted(
        (series["metric"]["version"], series["metric"]["status"], series["value"][1])
        for series in report["data"]["result"]
    )
    print(f"Prometheus | {QUERY}")
    print("VERSION  STATUS  COUNT")
    for version, status, count in rows:
        print(f"{version:<8} {status:<7} {count}")


if __name__ == "__main__":
    main()
