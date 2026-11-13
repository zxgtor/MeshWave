"""Persistent local fit jobs. Each solve runs in a cancellable child process."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted'}
MAX_QUEUED = 8


def read_json(path):
    # Atomic replacement can briefly deny reads on Windows. Retry opening the
    # file, but never hide missing files, invalid JSON, or persistent denial.
    for attempt in range(100):
        try:
            text = path.read_text(encoding='utf-8')
        except PermissionError:
            if attempt == 99:
                raise
            time.sleep(.01)
        else:
            return json.loads(text)


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    # Windows readers briefly hold a non-delete-sharing handle. Retain atomic
    # publication and retry that sharing violation instead of failing a solve.
    for attempt in range(100):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 99:
                raise
            time.sleep(.01)


class TaskBusy(ValueError):
    pass


class TaskManager:
    def __init__(self, root, solver):
        self.root = Path(root)
        self.solver = solver
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.stop = threading.Event()
        self.jobs = {}
        self.active = None
        self.thread = None
        if self.root.exists():
            for path in self.root.glob('*/task.json'):
                job = read_json(path)
                if job['status'] not in TERMINAL:
                    job.update(status='interrupted', updated=time.time(), error='Service restarted; submit a new task.')
                    write_json(path, job)
                self.jobs[job['id']] = job

    def path(self, task_id):
        if not isinstance(task_id, str) or len(task_id) != 32 or any(c not in '0123456789abcdef' for c in task_id):
            raise ValueError('Invalid task ID.')
        if task_id not in self.jobs:
            raise ValueError('Task not found.')
        return self.root / task_id

    def _save(self, job):
        job['updated'] = time.time()
        write_json(self.root / job['id'] / 'task.json', job)

    def submit(self, body):
        if not isinstance(body, dict) or not all(isinstance(body.get(k), str) for k in ('source', 'target')):
            raise ValueError('source and target must contain OBJ text.')
        if not isinstance(body.get('pairs'), list) or not 3 <= len(body['pairs']) <= 100:
            raise ValueError('Provide 3–100 correspondence pairs.')
        if len(body['source'].encode()) > 18 * 1024**2 or len(body['target'].encode()) > 18 * 1024**2:
            raise ValueError('Each OBJ must be at most 18 MB.')
        for key in ('sourceName', 'targetName'):
            if key in body and (not isinstance(body[key], str) or not 1 <= len(body[key]) <= 255):
                raise ValueError('Model names must be strings of 1–255 characters.')
        # The worker applies the existing solver validation to all constraints/settings.
        request = {k: body[k] for k in ('source', 'target', 'pairs', 'iterations', 'smoothness', 'normalAngle',
                   'solverMode', 'brushWeights', 'excludedFaces', 'sourceName', 'targetName') if k in body}
        with self.lock:
            if self.stop.is_set():
                raise TaskBusy('Service is shutting down.')
            if sum(j['status'] not in TERMINAL for j in self.jobs.values()) >= MAX_QUEUED:
                raise TaskBusy('Task queue is full (8).')
            task_id = uuid.uuid4().hex
            path = self.root / task_id
            path.mkdir(parents=True)
            write_json(path / 'input.json', request)
            job = dict(id=task_id, status='queued', created=time.time(), updated=time.time(),
                       sourceName=str(body.get('sourceName', 'template.obj'))[:255],
                       targetName=str(body.get('targetName', 'target.obj'))[:255])
            self.jobs[task_id] = job
            self._save(job)
            if self.thread is None:
                self.thread = threading.Thread(target=self._run, daemon=True)
                self.thread.start()
            self.wake.set()
            return self.status(task_id)

    def status(self, task_id):
        with self.lock:
            path = self.path(task_id)
            job = dict(self.jobs[task_id])
            progress = path / 'progress.json'
            if progress.exists():
                job['progress'] = read_json(progress)
            job['previewAvailable'] = (path / 'preview.json').exists()
            job['resultAvailable'] = job['status'] == 'completed'
            job['viewerUrl'] = '/?task=' + task_id
            return job

    def list(self):
        with self.lock:
            return [self.status(j['id']) for j in sorted(self.jobs.values(), key=lambda j: j['created'], reverse=True)[:50]]

    def read(self, task_id, artifact):
        if artifact not in ('input', 'preview', 'result'):
            raise ValueError('Unknown task artifact.')
        with self.lock:
            path = self.path(task_id)
            if artifact == 'result' and self.jobs[task_id]['status'] != 'completed':
                raise ValueError('No completed result; previews are not final results.')
            file = path / (artifact + '.json')
            if not file.exists():
                raise ValueError('Artifact is not available yet.')
            return read_json(file)

    def cancel(self, task_id):
        with self.lock:
            self.path(task_id)
            job = self.jobs[task_id]
            if job['status'] not in TERMINAL:
                job['status'] = 'cancelling' if self.active and self.active[0] == task_id else 'cancelled'
                self._save(job)
            self.wake.set()
            return self.status(task_id)

    def _run(self):
        while not self.stop.is_set():
            with self.lock:
                job = next((j for j in self.jobs.values() if j['status'] == 'queued'), None)
            if job is None:
                self.wake.wait(.25)
                self.wake.clear()
                continue
            if not self.solver.acquire(timeout=.25):
                continue
            process = None
            try:
                with self.lock:
                    if job['status'] != 'queued' or self.stop.is_set():
                        continue
                    path = self.root / job['id']
                    job['status'] = 'running'
                    self._save(job)
                    with (path / 'worker.log').open('w', encoding='utf-8') as log:
                        process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('task_worker.py')), str(path)],
                            stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                            env={**os.environ, 'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1'})
                    self.active = (job['id'], process)
                while process.poll() is None:
                    if self.stop.is_set() or job['status'] == 'cancelling':
                        process.terminate()
                        break
                    self.stop.wait(.05)
                process.wait(timeout=10)
                with self.lock:
                    if job['status'] == 'cancelling':
                        job['status'] = 'cancelled'
                    elif self.stop.is_set():
                        job['status'] = 'interrupted'
                    elif process.returncode == 0 and (path / 'result.json').exists():
                        job['status'] = 'completed'
                    else:
                        job['status'] = 'failed'
                        error = path / 'error.json'
                        job['error'] = read_json(error)['error'] if error.exists() else 'Solver process failed; see worker.log.'
                    self._save(job)
            except Exception as exc:
                if process and process.poll() is None:
                    process.kill()
                    process.wait()
                with self.lock:
                    job.update(status='failed', error=str(exc))
                    self._save(job)
            finally:
                with self.lock:
                    self.active = None
                self.solver.release()

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.thread:
            self.thread.join(12)
