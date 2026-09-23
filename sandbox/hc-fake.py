#!/usr/bin/env python3
# Fake Healthchecks.io: logs "METHOD PATH BODY" to /var/log/msp/hc-fake.log, answers 200 OK.
import http.server, sys
LOG = "/var/log/msp/hc-fake.log"
class H(http.server.BaseHTTPRequestHandler):
    def _log(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode(errors="replace") if n else ""
        with open(LOG, "a") as f: f.write(f"{self.command} {self.path} {body}\n")
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    do_GET = do_POST = _log
    def log_message(self, *a): pass
http.server.HTTPServer(("127.0.0.1", 8099), H).serve_forever()
