"""Private subprocess entry point; never started by clients directly."""
import json
from pathlib import Path
import sys
import time
import numpy as np
from task_service import write_json
from wrap_core import wrap


def main(path):
    body = json.loads((path / 'input.json').read_text(encoding='utf-8'))
    revision = 0

    def progress(event, vertices=None):
        nonlocal revision
        if vertices is not None:
            revision += 1
            write_json(path / 'preview.json', {'revision': revision, 'vertices': vertices.tolist(), 'stage': event['stage']})
        write_json(path / 'progress.json', {**event, 'previewRevision': revision, 'timestamp': time.time()})

    try:
        progress({'phase': 'preparing', 'stage': '', 'iteration': 0, 'requestedIterations': body.get('iterations', 20)})
        result = wrap(body['source'], body['target'], body['pairs'], body.get('iterations', 20),
            body.get('smoothness', 4), body.get('excludedFaces'), body.get('normalAngle', 60),
            body.get('solverMode', 'single'), body.get('brushWeights'), progress=progress)
        write_json(path / 'result.json', result)
        progress({'phase': 'finished', 'stage': '', 'iteration': result['stats']['iterations'],
                  'requestedIterations': result['stats']['requestedIterations']}, np.asarray(result['vertices']))
    except Exception as exc:
        write_json(path / 'error.json', {'error': str(exc)})
        raise


if __name__ == '__main__':
    main(Path(sys.argv[1]))
