"""Minimal fictional HTTP service backing the examples/ quickstart.

Standard-library only (http.server) — no new dependency, per the RF2
clarification in specs/002-publish-release/spec.md. Serves the /info
endpoints and API targets referenced by examples/config/environments/
example.json.dist and examples/scenarios/generic_example/*.json.

Run with: python examples/mock_server.py
Then, in another terminal: thomas request --environment
examples/config/environments/example.json --folder examples/scenarios
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

HOST = "127.0.0.1"
PORT = 8000


class MockHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path == "/instant-transfer/info":
            self._send_json(200, {"service": "instant-transfer-service", "status": "UP"})
        elif self.path == "/billing/info":
            self._send_json(200, {"service": "billing-service", "status": "UP"})
        else:
            self._send_json(404, {"error": {"code": "NOT_FOUND"}})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw_body) if raw_body else {}
        except ValueError:
            payload = {}

        if self.path == "/api/orders":
            self._handle_orders(payload)
        elif self.path == "/api/invoices":
            self._handle_invoices(payload)
        else:
            self._send_json(404, {"error": {"code": "NOT_FOUND"}})

    def _handle_orders(self, payload: dict) -> None:
        destination_key = payload.get("destination_key", "")
        if destination_key.startswith("nonexistent-"):
            self._send_json(422, {"error": {"code": "PAYMENT_KEY_NOT_FOUND"}})
            return
        order_id = f"order-{abs(hash(json.dumps(payload, sort_keys=True))) % 100000}"
        self._send_json(201, {"id": order_id, "status": "PENDING"})

    def _handle_invoices(self, payload: dict) -> None:
        invoice_id = f"invoice-{abs(hash(json.dumps(payload, sort_keys=True))) % 100000}"
        self._send_json(202, {"invoice_id": invoice_id})

    def log_message(self, format: str, *args) -> None:
        print(f"[mock_server] {self.address_string()} - {format % args}")


def main() -> None:
    server = HTTPServer((HOST, PORT), MockHandler)
    print(f"Mock service running at http://{HOST}:{PORT} — Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
