import argparse
import json
import socket
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import BoundedSemaphore
from urllib.parse import urlparse, parse_qs
from wrap_core import mesh_data, wrap, export_obj
from project import validate_project
from texture import normalize_texture, bake_texture, texture_bundle
from landmarks import generate_pairs
from brush_support import prepare_brush
from curves import generate_curve_pairs
from mesh_health import diagnose_mesh, repair_mesh
from optical_flow import refine_texture
from batch_jobs import BatchManager, BatchBusy, constraints_manifest

ROOT = Path(__file__).parent
SOLVER = BoundedSemaphore(1)
BATCH = BatchManager(ROOT / 'output' / 'batches', SOLVER)


class LocalServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.mjs': 'text/javascript'}

    def list_directory(self, path):
        self.send_error(404)

    def do_GET(self):
        request=urlparse(self.path)
        if request.path!='/api/batch-download':return super().do_GET()
        try:
            job_id=parse_qs(request.query).get('jobId',[''])[0];path=BATCH.download_path(job_id)
            self.send_response(200);self.send_header('Content-Type','application/zip');self.send_header('Content-Length',str(path.stat().st_size));self.send_header('Content-Disposition',f'attachment; filename="facewrap_batch_{job_id[:8]}.zip"');self.send_header('Cache-Control','no-store');self.end_headers()
            with path.open('rb') as stream:self.copyfile(stream,self.wfile)
        except BatchBusy as exc:self.reply(409,{'error':str(exc)})
        except ValueError as exc:self.reply(400,{'error':str(exc)})

    def do_POST(self):
        origin = self.headers.get('Origin')
        if origin and urlparse(origin).netloc != self.headers.get('Host'):
            self.reply(403, {'error': '仅允许同源请求。'})
            return
        try:
            size = int(self.headers.get('Content-Length', 0))
            if not 0 < size <= 96 * 1024 * 1024:
                raise ValueError('请求大小上限为 96 MB。')
            body = json.loads(self.rfile.read(size))
            if self.path == '/api/mesh':
                self.reply(200, mesh_data(body['text']))
            elif self.path == '/api/texture':
                self.reply(200, normalize_texture(body))
            elif self.path in ('/api/wrap', '/api/bake', '/api/landmarks', '/api/flow-refine'):
                if not SOLVER.acquire(blocking=False):
                    self.reply(409, {'error': '正在计算，请稍后重试。'})
                    return
                try:
                    if self.path == '/api/wrap':
                        result = wrap(body['source'], body['target'], body['pairs'],
                            body.get('iterations', 20), body.get('smoothness', 4), body.get('excludedFaces'), body.get('normalAngle', 60), body.get('solverMode', 'single'))
                    elif self.path == '/api/bake':
                        result = bake_texture(body['source'], body['target'], body['vertices'], body['targetTexture'],
                            body.get('resolution', 1024), body.get('padding', 8), body.get('distanceRatio', .02),
                            body.get('normalAngle', 60), body.get('excludedFaces'))
                    elif self.path == '/api/landmarks':
                        result = generate_pairs(body)
                    else:
                        result = refine_texture(body)
                    self.reply(200, result)
                finally:
                    SOLVER.release()
            elif self.path == '/api/export':
                self.reply(200, {'text': export_obj(body['source'], body['vertices'])})
            elif self.path == '/api/project':
                self.reply(200, validate_project(body))
            elif self.path == '/api/brush-reference':
                self.reply(200, prepare_brush(body))
            elif self.path == '/api/curve-pairs':
                self.reply(200, generate_curve_pairs(body))
            elif self.path == '/api/mesh-diagnose':
                self.reply(200, diagnose_mesh(body))
            elif self.path == '/api/mesh-repair':
                self.reply(200, repair_mesh(body))
            elif self.path == '/api/batch-constraints':
                self.reply(200, constraints_manifest(body))
            elif self.path == '/api/batch-create':
                self.reply(200, BATCH.create(body))
            elif self.path == '/api/batch-add':
                self.reply(200, BATCH.add(body))
            elif self.path == '/api/batch-start':
                self.reply(200, BATCH.start(body['jobId']))
            elif self.path == '/api/batch-status':
                self.reply(200, BATCH.status(body['jobId']))
            elif self.path == '/api/batch-cancel':
                self.reply(200, BATCH.cancel(body['jobId']))
            elif self.path == '/api/texture-export':
                self.binary_reply(200, texture_bundle(body['source'], body['vertices'], body['texture']), 'application/zip')
            else:
                self.reply(404, {'error': '接口不存在。'})
        except BatchBusy as exc:
            self.reply(409, {'error': str(exc)})
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            self.reply(400, {'error': str(exc)})
        except Exception as exc:
            print(f'Solver error: {exc!r}', flush=True)
            self.reply(500, {'error': '计算失败，请检查模型或查看本地服务日志。'})

    def reply(self, status, data):
        payload = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.binary_reply(status, payload, 'application/json; charset=utf-8')

    def binary_reply(self, status, payload, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=6188)
    args = parser.parse_args()
    server = LocalServer(('127.0.0.1', args.port), partial(Handler, directory=str(ROOT / 'web')))
    print(f'Mesh Wave: http://127.0.0.1:{args.port}', flush=True)
    server.serve_forever()
