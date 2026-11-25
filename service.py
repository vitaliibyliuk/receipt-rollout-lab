import json
import os
import re
from datetime import datetime, timezone
from uuid import uuid4

from flask import Flask, Response, g, request
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, generate_latest

from ledger import Ledger
from release import VERSION, confirm

GROUP_CODE = re.compile(r"SE-[0-9]{2}")


def create_app():
    app = Flask(__name__)
    ledger = Ledger(os.getenv("SUBMIT_DB", "receipts.sqlite"))
    interrupted = os.getenv("FAIL_CONFIRMATION") == "1"
    registry = CollectorRegistry()
    responses = Counter(
        "submission_responses_total", "HTTP results for new and repeated submissions",
        ("version", "status"), registry=registry,
    )

    def write_event(event, status):
        data = {
            "time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "request_id": g.trace,
            "version": VERSION,
            "event": event,
            "status": status,
        }
        if g.number is not None:
            data["submission_id"] = g.number
        print(json.dumps(data, separators=(",", ":")), flush=True)

    @app.before_request
    def start_trace():
        g.trace = uuid4().hex
        g.number = None

    @app.after_request
    def finish_trace(response):
        response.headers["X-Request-Id"] = g.trace
        if request.endpoint == "submit" and request.method == "POST":
            responses.labels(version=VERSION, status=str(response.status_code)).inc()
            write_event("submission_response", response.status_code)
        return response

    @app.get("/health")
    def health():
        return {"version": VERSION, "status": "ok"}

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(registry), content_type=CONTENT_TYPE_LATEST)

    @app.post("/submissions")
    def submit():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return {"error": "Expected a JSON object"}, 400
        group = payload.get("group_code")
        key = payload.get("submission_key")
        if not isinstance(group, str) or GROUP_CODE.fullmatch(group) is None:
            return {"error": "Invalid group format"}, 400
        if not isinstance(key, str) or not key.strip() or len(key) > 64:
            return {"error": "Invalid submission key"}, 400

        row, inserted = ledger.register(group, key)
        g.number = row["id"]
        if row["group_code"] != group:
            return {"error": "Key already belongs to another group"}, 409
        if not inserted:
            return {"id": g.number}, 200

        write_event("submission_saved", 201)
        try:
            receipt = confirm(g.number, interrupted)
        except TimeoutError:
            write_event("confirmation_failed", 503)
            return {"id": g.number, "error": "Receipt timed out"}, 503

        result = {"id": g.number}
        if receipt is not None:
            result["receipt"] = receipt
            write_event("confirmation_sent", 201)
        return result, 201

    @app.get("/submissions/<int:number>")
    def lookup(number):
        row = ledger.find(number)
        return row if row is not None else ({"error": "Unknown submission"}, 404)

    return app
