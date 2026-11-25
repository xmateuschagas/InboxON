"""Serve a interface do InboxON no computador com o túnel SSH aberto."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

HOST = "127.0.0.1"
PORT = 8787
ORIGIN = f"http://{HOST}:{PORT}"
UPSTREAM = "http://127.0.0.1:15678/webhook/classificar-mensagem"
PAGE = Path(__file__).with_name("index.html")
DIRECT = build_opener(ProxyHandler({}))


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def json_reply(self, status, data):
        self.reply(status, "application/json; charset=utf-8", json.dumps(data).encode("utf-8"))

    def do_GET(self):
        if self.path not in ("/", "/index.html") or self.headers.get("Host") != f"{HOST}:{PORT}":
            self.json_reply(404, {"erro": "Página não encontrada."})
            return
        self.reply(200, "text/html; charset=utf-8", PAGE.read_bytes())

    def do_POST(self):
        if self.path != "/classificar" or self.headers.get("Host") != f"{HOST}:{PORT}":
            self.json_reply(404, {"erro": "Rota não encontrada."})
            return
        if self.headers.get("Origin") != ORIGIN:
            self.json_reply(403, {"erro": "Abra a página pelo endereço local indicado."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 40000 or self.headers.get_content_type() != "application/json":
                raise ValueError()
            data = json.loads(self.rfile.read(size))
            message = data.get("mensagem") if isinstance(data, dict) else None
            if not isinstance(message, str) or not 1 <= len(message.strip()) <= 3000:
                raise ValueError()
        except (ValueError, UnicodeError):
            self.json_reply(422, {"erro": "Envie uma mensagem de 1 a 3.000 caracteres."})
            return

        request = Request(
            UPSTREAM,
            data=json.dumps({"mensagem": message.strip()}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with DIRECT.open(request, timeout=58) as response:
                result = json.loads(response.read(65536))
                status = response.status
        except HTTPError as error:
            status = error.code
            result = {"erro": f"O webhook retornou HTTP {status}."}
        except (URLError, TimeoutError, ValueError, UnicodeError):
            status = 502
            result = {"erro": "A VPS não respondeu. Confira o túnel SSH na porta 15678."}
        self.json_reply(status, result)


if __name__ == "__main__":
    if not PAGE.is_file():
        raise SystemExit("Coloque index.html na mesma pasta de servidor.py.")
    with ThreadingHTTPServer((HOST, PORT), Handler) as server:
        print(f"Abra {ORIGIN} no navegador. Pressione Ctrl+C para sair.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
