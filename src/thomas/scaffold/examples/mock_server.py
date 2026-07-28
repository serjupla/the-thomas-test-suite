#!/usr/bin/env python3
"""Mock server for Thomas examples."""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, ClassVar


class MockHandler(BaseHTTPRequestHandler):
    """Simple HTTP request handler for mock API."""

    # In-memory state for demo purposes
    _charges: ClassVar[dict[str, Any]] = {}
    _charge_counter: ClassVar[int] = 1000

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        """Handle POST requests."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        if self.path == "/charges":
            self._handle_charges(body)
        elif self.path == "/transfers":
            self._handle_transfers(body)
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_charges(self, body: bytes):
        """Handle POST /charges request."""
        try:
            payload = json.loads(body)

            # Mock logic: create charge
            MockHandler._charge_counter += 1
            charge_id = f"CHARGE-{MockHandler._charge_counter}"
            charge = {
                "charge_id": charge_id,
                "customer_id": payload.get("customer_id"),
                "amount": payload.get("amount"),
                "status": "completed",
            }
            MockHandler._charges[charge_id] = charge

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(charge).encode())
        except ValueError:
            self.send_response(400)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode())

    def _handle_transfers(self, body: bytes):
        """Handle POST /transfers request."""
        try:
            payload = json.loads(body)

            # Mock logic: validate account, then transfer
            account = payload.get("account_id", "")
            if not account or not account.startswith("ACC-"):
                # Invalid account
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"error": "Invalid account_id"}).encode()
                )
                return

            # Valid transfer
            transfer = {
                "transfer_id": f"TXN-{MockHandler._charge_counter}",
                "account_id": account,
                "amount": payload.get("amount"),
                "status": "completed",
            }
            MockHandler._charge_counter += 1

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(transfer).encode())
        except ValueError:
            self.send_response(500)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode())

    def log_message(self, format, *args):
        """Suppress default logging."""


def main():
    """Start mock server."""
    port = int(os.getenv("MOCK_SERVER_PORT", "8000"))
    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, MockHandler)

    print(f"Mock server listening on http://127.0.0.1:{port}")
    print("Press Ctrl+C to stop")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        httpd.shutdown()


if __name__ == "__main__":
    main()
