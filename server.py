"""Loopback-only API and production static server for Atelier."""
import argparse
import json
import threading
import logging
import mimetypes
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from inventory import scan
from project_details import describe

ROOT = Path(__file__).resolve().parent
cache = None
scan_lock = threading.Lock()
details_lock = threading.Lock()
details_cache = {}

def inventory(refresh=False):
    global cache
    with scan_lock:
        if cache is None or refresh:
            cache = scan()
            details_cache.clear()
        return cache

def project_details(project_id):
    data = inventory()
    project = next((p for p in data['projects'] if p['id'] == project_id), None)
    if not project:
        return None, None
    with details_lock:
        key = (data['scannedAt'], project_id)
        if key not in details_cache:
            details_cache[key] = describe(project['path'], project, data['projects'])
        return project, details_cache[key]

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT/'dist'), **kwargs)

    def valid_host(self):
        return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

    def send_json(self, value, code=200):
        payload = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if not self.valid_host():
            return self.send_json({'error': 'Hôte non autorisé'}, 403)
        route = urlsplit(self.path).path
        if route.startswith('/api/projects/'):
            parts = route.strip('/').split('/')
            if len(parts) not in {3,4} or len(parts)==4 and parts[3]!='media':
                return self.send_json({'error':'Route inconnue'},404)
            try:
                project, detail = project_details(parts[2])
                if not project: return self.send_json({'error':'Projet inconnu'},404)
                if len(parts)==3: return self.send_json(detail)
                relative = parse_qs(urlsplit(self.path).query).get('path',[''])[0]
                if relative not in {s['path'] for s in detail['screenshots']}:
                    return self.send_json({'error':'Capture inconnue'},404)
                root = Path(project['path']).resolve()
                image = (root/relative).resolve()
                if not image.is_relative_to(root) or image.stat().st_size>15_000_000:
                    return self.send_json({'error':'Capture non disponible'},403)
                payload = image.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type',mimetypes.guess_type(str(image))[0] or 'application/octet-stream')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Cache-Control','private, max-age=60')
                self.send_header('Content-Length',str(len(payload)))
                self.end_headers();self.wfile.write(payload)
                return
            except Exception:
                logging.exception('Analyse de fiche impossible')
                return self.send_json({'error':'Les détails de ce projet sont indisponibles.'},500)
        if route == '/api/projects':
            try:
                return self.send_json(inventory())
            except Exception:
                return self.send_json({'error': 'L’inventaire a échoué. Consulter le terminal du serveur.'}, 500)
        if route.startswith('/api/'):
            return self.send_json({'error': 'Route inconnue'}, 404)
        return super().do_GET()

    def do_POST(self):
        origin = self.headers.get('Origin')
        if not self.valid_host() or origin not in {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}', 'http://127.0.0.1:5173'}:
            return self.send_json({'error': 'Origine non autorisée'}, 403)
        if urlsplit(self.path).path != '/api/refresh':
            return self.send_json({'error': 'Route inconnue'}, 404)
        try:
            return self.send_json(inventory(refresh=True))
        except Exception:
            return self.send_json({'error': 'L’actualisation a échoué. Réessayez.'}, 500)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    if not (ROOT/'dist'/'index.html').exists():
        raise SystemExit('Construire l’interface avec npm install puis npm run build.')
    print(f'Atelier · http://127.0.0.1:{args.port} · Ctrl+C pour arrêter', flush=True)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nAtelier arrêté.', flush=True)
    finally:
        server.server_close()
