"""Serve the isolated build and proxy only to the disposable API."""
import http.client
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BUILD = Path("/tmp/cygnusx-run-claims-build")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BUILD), **kwargs)

    def proxy(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        headers = {k: v for k, v in self.headers.items() if k.lower() not in {"host", "connection"}}
        connection = http.client.HTTPConnection("127.0.0.1", 18026, timeout=30)
        connection.request(self.command, self.path, body, headers)
        response = connection.getresponse()
        content = response.read()
        self.send_response(response.status)
        for key, value in response.getheaders():
            if key.lower() not in {"transfer-encoding", "connection", "content-length"}:
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)
        connection.close()

    def do_GET(self):
        if self.path.startswith(("/api/", "/health")):
            return self.proxy()
        if not (BUILD / self.path.split("?")[0].lstrip("/")).is_file():
            self.path = "/index.html"
        return super().do_GET()

    do_POST = proxy
    do_PATCH = proxy
    do_DELETE = proxy
    do_PUT = proxy

    def log_message(self, *args):
        pass


ThreadingHTTPServer(("127.0.0.1", 18023), Handler).serve_forever()
