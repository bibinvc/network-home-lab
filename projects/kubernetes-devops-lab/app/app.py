"""Small read-only workload for the infrastructure lab, not a production portal."""
import html
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


def inventory():
    import psycopg
    with psycopg.connect(host=os.environ['PGHOST'], port=5432,
                        dbname='ops', user='app_reader',
                        password=os.environ['PGPASSWORD'], connect_timeout=3,
                        options='-c statement_timeout=2000') as connection:
        rows = connection.execute(
            'SELECT hostname, purpose, status FROM inventory ORDER BY hostname LIMIT 100'
        ).fetchall()
    return [dict(zip(('hostname', 'purpose', 'status'), row)) for row in rows]


def handler(loader=inventory):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'OpsLab'

        def log_message(self, *_):
            # Do not print credentials, request headers or raw query strings.
            print(json.dumps({'event': 'http_request', 'path': urlsplit(self.path).path}), flush=True)

        def respond(self, code, body, content_type='application/json'):
            payload = body.encode() if isinstance(body, str) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header('Content-Type', content_type + '; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            self.respond(405, {'error': 'read_only_workload'})

        do_PUT = do_PATCH = do_DELETE = do_POST

        def do_GET(self):
            path = urlsplit(self.path).path
            release = os.environ.get('APP_RELEASE', '1.0.0')
            if path == '/healthz':
                return self.respond(200, {'status': 'alive'})
            if path == '/version':
                return self.respond(200, {'release': release})
            if path not in ['/', '/records', '/readyz', '/metrics']:
                return self.respond(404, {'error': 'not_found'})
            if path == '/readyz' and os.environ.get('APP_FORCE_UNREADY') == '1':
                return self.respond(503, {'error': 'readiness_drill'})
            try:
                rows = loader()
            except Exception:
                return self.respond(503, {'error': 'database_unavailable'})
            if path == '/records':
                return self.respond(200, {'count': len(rows), 'records': rows})
            if path == '/readyz':
                return self.respond(200, {'status': 'ready'})
            if path == '/metrics':
                return self.respond(200, '# TYPE ops_inventory_records gauge\nops_inventory_records %d\n' % len(rows), 'text/plain')
            table = ''.join('<tr>' + ''.join('<td>' + html.escape(str(row[key])) + '</td>'
                                           for key in ('hostname', 'purpose', 'status')) + '</tr>'
                            for row in rows)
            page = '''<!doctype html><html lang="en"><meta charset="utf-8">
            <meta name="viewport" content="width=device-width,initial-scale=1">
            <title>Infrastructure Operations Lab</title><style>
            body{font:16px system-ui;background:#101b2b;color:#e6eef9;max-width:950px;margin:50px auto;padding:20px}
            h1{font-size:32px}small{color:#9db3cd}.card{background:#1b2c43;border:1px solid #3b536e;border-radius:12px;padding:24px;margin:20px 0}
            table{width:100%%;border-collapse:collapse}td,th{text-align:left;padding:12px;border-bottom:1px solid #3b536e}
            .badge{color:#9ce5c3}p{line-height:1.6}</style>
            <small>PERSONAL INFRASTRUCTURE LAB · SYNTHETIC INVENTORY</small>
            <h1>Infrastructure Operations Lab</h1><p>Release <b>%s</b> · <span class="badge">Read-only workload</span></p>
            <div class="card"><h2>Deployment path</h2><p>Local access → ModSecurity / OWASP CRS WAF → Kubernetes service → application replicas → PostgreSQL</p>
            <p>Configuration, migration, rollout and recovery checks are recorded in the repository evidence.</p></div>
            <div class="card"><h2>Lab inventory · %d records</h2><table><tr><th>Host</th><th>Purpose</th><th>Status</th></tr>%s</table></div>
            <small>This page does not certify production security, high availability or a performance SLA.</small></html>''' % (html.escape(release), len(rows), table)
            self.respond(200, page, 'text/html')
    return Handler


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '8080'))), handler()).serve_forever()
