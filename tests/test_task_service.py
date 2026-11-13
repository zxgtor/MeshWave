import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from functools import partial
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import numpy as np
import server
from task_service import TaskManager, TERMINAL, read_json
from test_core import fixture
from wrap_core import wrap


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.solver = threading.BoundedSemaphore(1)
        self.manager = TaskManager(Path(self.tmp.name), self.solver)
        a, b, pairs, self.target = fixture()
        self.body = dict(source=a, target=b, pairs=pairs, iterations=5, solverMode='multistage')

    def tearDown(self):
        self.manager.close()
        self.tmp.cleanup()

    def wait(self, task_id, predicate=lambda j: j['status'] in TERMINAL):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            job = self.manager.status(task_id)
            if predicate(job):
                return job
            time.sleep(.02)
        self.fail('Task timed out: ' + str(job))

    def test_real_fit_preview_export_and_constraints(self):
        task = self.manager.submit(self.body)
        finished = self.wait(task['id'])
        self.assertEqual(finished['status'], 'completed', finished)
        self.assertTrue(finished['previewAvailable'])
        self.assertGreaterEqual(finished['progress']['previewRevision'], 3)
        result = self.manager.read(task['id'], 'result')
        points = np.array(self.body['pairs'])
        np.testing.assert_allclose(np.array(result['vertices'])[points[:, 0]], self.target[points[:, 1]], atol=1e-10)
        self.assertGreater(result['stats']['minimumProjectedAreaRatio'], .01)
        self.assertTrue(self.solver.acquire(False))
        self.solver.release()

    def test_running_cancel_releases_solver_and_next_job_succeeds(self):
        task = self.manager.submit(self.body)
        self.wait(task['id'], lambda j: j['status'] == 'running')
        self.manager.cancel(task['id'])
        self.assertEqual(self.wait(task['id'])['status'], 'cancelled')
        with self.assertRaises(ValueError):
            self.manager.read(task['id'], 'result')
        second = self.manager.submit(self.body)
        self.assertEqual(self.wait(second['id'])['status'], 'completed')

    def test_queued_cancel_and_recovery_after_restart(self):
        self.solver.acquire()
        try:
            first = self.manager.submit(self.body)
            self.manager.cancel(first['id'])
            self.assertEqual(self.manager.status(first['id'])['status'], 'cancelled')
            second = self.manager.submit(self.body)
            self.manager.close()
            restored = TaskManager(Path(self.tmp.name), self.solver)
            self.assertEqual(restored.status(second['id'])['status'], 'interrupted')
            restored.close()
        finally:
            self.solver.release()

    def test_invalid_fit_fails_without_poisoning_queue(self):
        with self.assertRaises(ValueError):
            self.manager.submit({**self.body, 'sourceName': {}})
        failed = self.manager.submit({**self.body, 'pairs': [[999999, 1], [2, 2], [3, 3]]})
        self.assertEqual(self.wait(failed['id'])['status'], 'failed')
        self.assertIn('error', self.manager.status(failed['id']))
        second = self.manager.submit(self.body)
        self.assertEqual(self.wait(second['id'])['status'], 'completed')
        for invalid in ['../secret', 'a'*31, 'z'*32]:
            with self.assertRaises(ValueError):
                self.manager.read(invalid, 'input')

    def test_progress_poll_recovers_from_temporary_read_lock(self):
        self.solver.acquire()
        try:
            job = self.manager.submit(self.body)
            progress = Path(self.tmp.name) / job['id'] / 'progress.json'
            progress.write_text(json.dumps({'iteration': 2}), encoding='utf-8')
            real_read = Path.read_text
            attempts = []
            def locked_read(path, *args, **kwargs):
                if path == progress:
                    attempts.append(path)
                    if len(attempts) <= 2:
                        raise PermissionError(13, 'File temporarily locked', str(path))
                return real_read(path, *args, **kwargs)
            with patch.object(Path, 'read_text', new=locked_read):
                self.assertEqual(self.manager.status(job['id'])['progress']['iteration'], 2)
                self.assertEqual(self.manager.list()[0]['progress']['iteration'], 2)
            self.assertEqual(len(attempts), 4)
        finally:
            self.solver.release()

    def test_callbacks_do_not_change_either_solver(self):
        for weights in (None, [1.] * len(self.target)):
            events = []
            base = wrap(self.body['source'], self.body['target'], self.body['pairs'], 5, brush_weights=weights)
            seen = wrap(self.body['source'], self.body['target'], self.body['pairs'], 5, brush_weights=weights,
                        progress=lambda e, v=None: events.append((e, v)))
            np.testing.assert_array_equal(base['vertices'], seen['vertices'])
            self.assertEqual([e['iteration'] for e, v in events if v is None], list(range(1, 6)))
            self.assertTrue(any(v is not None for e, v in events))

    def test_headless_http_lifecycle(self):
        http = server.LocalServer(('127.0.0.1', 0), partial(server.Handler, directory='web'))
        http.headless = True
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:' + str(http.server_address[1])
        def call(path, body=None):
            req = Request(base + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
            with urlopen(req, timeout=10) as response:
                raw = response.read()
                return raw.decode() if path.endswith('/export') else json.loads(raw)
        try:
            with patch.object(server, 'TASKS', self.manager):
                self.assertTrue(call('/api/health')['headless'])
                with self.assertRaises(HTTPError):
                    urlopen(base + '/')
                job = call('/api/tasks', self.body)
                self.wait(job['id'])
                root = '/api/tasks/' + job['id']
                self.assertEqual(call(root)['status'], 'completed')
                self.assertEqual(call(root + '/input')['pairs'], self.body['pairs'])
                self.assertIn('vertices', call(root + '/preview'))
                self.assertIn('stats', call(root + '/result'))
                self.assertIn('f ', call(root + '/export'))
                self.assertTrue(call('/api/tasks')['tasks'])
                self.assertEqual(call(root + '/cancel', {})['status'], 'completed')
        finally:
            http.shutdown()
            http.server_close()
            thread.join(5)


class JsonReadTests(unittest.TestCase):
    def test_permanent_permission_error_has_bounded_retries(self):
        with patch.object(Path, 'read_text', side_effect=PermissionError(13, 'Denied')) as read, \
                patch('task_service.time.sleep') as sleep:
            with self.assertRaises(PermissionError):
                read_json(Path('progress.json'))
            self.assertEqual(read.call_count, 100)
            self.assertEqual(sleep.call_count, 99)
            sleep.assert_called_with(.01)

    def test_missing_or_corrupt_file_is_not_retried(self):
        with tempfile.TemporaryDirectory() as folder, patch('task_service.time.sleep') as sleep:
            path = Path(folder) / 'progress.json'
            with self.assertRaises(FileNotFoundError):
                read_json(path)
            path.write_text('{', encoding='utf-8')
            with self.assertRaises(json.JSONDecodeError):
                read_json(path)
            sleep.assert_not_called()

    @unittest.skipUnless(os.name == 'nt', 'Windows sharing semantics')
    def test_real_windows_exclusive_handle_is_retried(self):
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'progress.json'
            path.write_text('{"iteration": 3}', encoding='utf-8')
            handle = kernel.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)
            if handle == ctypes.c_void_p(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
            closed = False
            def release(_):
                nonlocal closed
                self.assertTrue(kernel.CloseHandle(handle))
                closed = True
            try:
                with patch('task_service.time.sleep', side_effect=release) as sleep:
                    self.assertEqual(read_json(path), {'iteration': 3})
                    sleep.assert_called_once_with(.01)
            finally:
                if not closed:
                    kernel.CloseHandle(handle)


if __name__ == '__main__':
    unittest.main()
