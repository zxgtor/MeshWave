"""MCP adapter for the same HTTP task service used by the web UI."""
import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from mcp.server.fastmcp import FastMCP

BASE_URL = 'http://127.0.0.1:6188'
mcp = FastMCP('Mesh Wave', instructions='Fit OBJ templates to OBJ scans. Correspondences and region/weight constraints are required inputs, not inferred anatomy. Submit, monitor, inspect in the viewer, then export. Cancelled previews are not completed results.', host='127.0.0.1', port=6189)


def request(path, body=None, raw=False):
    data = None if body is None else json.dumps(body).encode('utf-8')
    req = Request(BASE_URL + path, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urlopen(req, timeout=60) as response:
            payload = response.read()
            return payload if raw else json.loads(payload)
    except HTTPError as exc:
        raise ValueError(exc.read().decode('utf-8', errors='replace')) from exc


def task_path(task_id):
    if len(task_id) != 32 or any(c not in '0123456789abcdef' for c in task_id):
        raise ValueError('Invalid task ID.')
    return '/api/tasks/' + task_id


@mcp.tool()
def service_health() -> dict:
    """Check the running Mesh Wave API service before using other tools."""
    return request('/api/health')


@mcp.tool()
def submit_fit(request_path: str, source_path: str | None = None, target_path: str | None = None) -> dict:
    """Submit a fit from local UTF-8 JSON. Supply source_path AND target_path to read OBJ files directly: JSON then contains only pairs and optional iterations, smoothness, solverMode, normalAngle, excludedFaces, brushWeights. Without paths JSON must include source/target OBJ text. Returns task ID and viewer URL; does not wait. All paths are on the MCP server's computer."""
    path = Path(request_path).resolve(strict=True)
    if path.stat().st_size > 96 * 1024**2:
        raise ValueError('Fit request exceeds 96 MB.')
    body = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(body, dict):
        raise ValueError('Request JSON must be an object.')
    if (source_path is None) != (target_path is None):
        raise ValueError('Supply both source_path and target_path.')
    if source_path is not None:
        for side, filename in [('source', source_path), ('target', target_path)]:
            model = Path(filename).resolve(strict=True)
            if model.stat().st_size > 18 * 1024**2:
                raise ValueError('Each OBJ must be at most 18 MB.')
            body[side] = model.read_text(encoding='utf-8-sig')
            body[side + 'Name'] = model.name
    result = request('/api/tasks', body)
    result['viewerUrl'] = BASE_URL + result['viewerUrl']
    return result


@mcp.tool()
def list_tasks() -> dict:
    """List the latest 50 shared fit jobs, including jobs submitted by the web UI or HTTP applications."""
    return request('/api/tasks')


@mcp.tool()
def get_task(task_id: str) -> dict:
    """Get status, real solver iteration/stage progress, errors and preview availability. Poll with reasonable intervals. Completed may still mean flip-protection stopped the solve early; inspect result statistics."""
    result = request(task_path(task_id))
    result['viewerUrl'] = BASE_URL + result['viewerUrl']
    return result


@mcp.tool()
def cancel_task(task_id: str) -> dict:
    """Cancel a queued or running fit. Running changes to cancelling until its worker stops; no final result is published."""
    return request(task_path(task_id) + '/cancel', {})


@mcp.tool()
def save_preview(task_id: str, output_path: str) -> dict:
    """Save latest stage geometry JSON to a NEW local file, without flooding AI context with vertices. Includes revision/stage; it is a non-final preview. Open viewerUrl to inspect interactively."""
    data = request(task_path(task_id) + '/preview', raw=True)
    path = Path(output_path).resolve()
    with path.open('xb') as output:
        output.write(data)
    return {'path': str(path), 'bytes': len(data), 'viewerUrl': BASE_URL + '/?task=' + task_id}


@mcp.tool()
def export_result(task_id: str, output_path: str) -> dict:
    """Save a completed task as a NEW OBJ, preserving source topology and UVs. Never overwrites a file. Returns quality/guard statistics too. Export is unavailable for failed/cancelled jobs."""
    data = request(task_path(task_id) + '/export', raw=True)
    result = request(task_path(task_id) + '/result')
    path = Path(output_path).resolve()
    with path.open('xb') as output:
        output.write(data)
    return {'path': str(path), 'bytes': len(data), 'stats': result['stats']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--api-url', default=BASE_URL)
    parser.add_argument('--transport', choices=['stdio', 'streamable-http'], default='stdio')
    parser.add_argument('--port', type=int, default=6189, help='Local Streamable HTTP MCP port')
    args = parser.parse_args()
    parsed = urlsplit(args.api_url)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.username:
        parser.error('--api-url must be a local HTTP service origin')
    BASE_URL = args.api_url.rstrip('/')
    mcp.settings.port = args.port
    mcp.run(transport=args.transport)
