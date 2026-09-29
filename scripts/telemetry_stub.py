"""
A local stand-in for the telemetry collector, for validating what an install
sends. Standard library only.

    python scripts/telemetry_stub.py            # listens on 0.0.0.0:9999
    python scripts/telemetry_stub.py --port 9000

Then point the install at it:

    FLAGWARD_TELEMETRY_URL=http://localhost:9999 python manage.py telemetry --send

From a compose container, use http://host.docker.internal:9999 instead.
Every received payload is printed as indented JSON.
"""
import argparse
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        received = datetime.now().isoformat(timespec="seconds")
        print(f"--- {received} {self.path} ({self.headers.get('User-Agent')})")
        try:
            print(json.dumps(json.loads(body), indent=2))
        except ValueError:
            print(f"(not JSON) {body!r}")
        print(flush=True)
        self.send_response(204)
        self.end_headers()

    def log_message(self, format, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9999)
    args = parser.parse_args()
    print(f"Telemetry stub listening on http://{args.host}:{args.port}", flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
