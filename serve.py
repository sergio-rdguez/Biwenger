#!/usr/bin/env python3
"""Servidor local: web de consulta + API de sync Biwenger (credenciales solo en .env)."""

from __future__ import annotations

import argparse
import functools
import json
import sys
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# Rutas que nunca deben servirse por HTTP aunque cuelguen de ROOT
# (credenciales, control de versiones, hoja de origen).
BLOCKED_PREFIXES = (".env", ".git", "Biwenger_2026.xlsx")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        print(f"[web] {self.address_string()} - {fmt % args}")

    def _is_blocked(self) -> bool:
        segments = [s for s in urlparse(self.path).path.split("/") if s]
        if not segments:
            return False
        # Bloquea dotfiles/dotdirs en cualquier nivel (.env, .git/…) y archivos concretos.
        return any(seg.startswith(".") for seg in segments) or segments[0] in BLOCKED_PREFIXES

    def do_GET(self) -> None:
        if self._is_blocked():
            self.send_error(403, "Forbidden")
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        if self._is_blocked():
            self.send_error(403, "Forbidden")
            return
        super().do_HEAD()

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            return
        self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/sync":
            self._handle_sync()
            return
        self.send_error(404)

    def _handle_sync(self) -> None:
        try:
            from sync_biwenger import sync

            data = sync(dry_run=False)
            # Nunca devolver credenciales; solo resumen + liga
            players = data.get("players") or []
            jornadas = {
                j
                for p in players
                for j in (p.get("positions") or {})
            }
            self._json(
                200,
                {
                    "ok": True,
                    "message": "Datos importados desde Biwenger",
                    "league_name": data.get("league_name"),
                    "season": data.get("season"),
                    "updated_at": data.get("updated_at"),
                    "managers": len(players),
                    "jornadas": len(jornadas),
                    "data": data,
                },
            )
        except Exception as exc:
            traceback.print_exc()
            self._json(500, {"ok": False, "error": str(exc)})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Interfaz donde escuchar. Por defecto solo localhost: /api/sync "
        "dispara un login real en Biwenger sin autenticación propia, así que "
        "abrirlo a la red (0.0.0.0) expone esa acción a cualquiera en tu WiFi.",
    )
    args = parser.parse_args()

    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"⚠ Escuchando en {args.host}: /api/sync quedará accesible para toda la red.")

    # Evita "Address already in use" al reiniciar en Windows
    ThreadingHTTPServer.allow_reuse_address = True
    with ThreadingHTTPServer((args.host, args.port), functools.partial(Handler)) as httpd:
        print(f"BOTE listo en http://127.0.0.1:{args.port}/web/")
        print(f"Sync API  POST http://127.0.0.1:{args.port}/api/sync")
        print("Ctrl+C para parar")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nParado.")


if __name__ == "__main__":
    main()
