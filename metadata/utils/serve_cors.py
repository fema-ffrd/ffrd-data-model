#!/usr/bin/env python3
"""Serve a directory over HTTP with permissive CORS headers."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class CORSRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", type=int, nargs="?", default=8000)
    parser.add_argument(
        "--bind", default="127.0.0.1", help="Interface to bind (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path.cwd(),
        help="Directory to serve (default: current working directory)",
    )
    args = parser.parse_args()
    directory = args.directory.expanduser().resolve()
    if not directory.is_dir():
        parser.error(f"not a directory: {directory}")

    handler = partial(CORSRequestHandler, directory=str(directory))
    with ThreadingHTTPServer((args.bind, args.port), handler) as server:
        print(f"Serving {directory} on http://{args.bind}:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
