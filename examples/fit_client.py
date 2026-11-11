"""Plain HTTP client: no MCP dependency. See docs/automation.md."""
import argparse
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--api-url', default='http://127.0.0.1:6188')
    parser.add_argument('--source', required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--constraints', required=True, help='JSON object with pairs and optional existing fit settings/regions/weights')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    destination = Path(args.output)
    if destination.exists():
        parser.error('Output already exists; choose a new filename.')
    def api(path, body=None, raw=False):
        data = None if body is None else json.dumps(body).encode('utf-8')
        with urlopen(Request(args.api_url.rstrip('/') + path, data=data, headers={'Content-Type':'application/json'}), timeout=60) as response:
            payload = response.read()
            return payload if raw else json.loads(payload)
    source, target = Path(args.source), Path(args.target)
    body = {**json.loads(Path(args.constraints).read_text(encoding='utf-8-sig')),
            'source':source.read_text(encoding='utf-8-sig'), 'target':target.read_text(encoding='utf-8-sig'),
            'sourceName':source.name, 'targetName':target.name}
    job = api('/api/tasks', body)
    path = '/api/tasks/' + job['id']
    print('Viewer:', args.api_url.rstrip('/') + job['viewerUrl'], flush=True)
    try:
        while True:
            job = api(path)
            print(json.dumps({'status':job['status'],'progress':job.get('progress')}, ensure_ascii=True), flush=True)
            if job['status'] in ('completed','failed','cancelled','interrupted'):
                break
            time.sleep(1)
        if job['status'] != 'completed':
            raise RuntimeError(job.get('error', job['status']))
        data = api(path + '/export', raw=True)
        with destination.open('xb') as output:
            output.write(data)
        print('Saved:', str(destination.resolve()))
    except KeyboardInterrupt:
        api(path + '/cancel', {})
        raise


if __name__ == '__main__':
    main()
