"""Optional real MCP protocol smoke test (install requirements-mcp.txt)."""
import asyncio
from functools import partial
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import server
from task_service import TaskManager
from test_core import fixture


@unittest.skipUnless(importlib.util.find_spec('mcp'), 'Optional MCP SDK is not installed')
class MCPTests(unittest.TestCase):
    def test_real_stdio_fit_preview_export_and_cancel(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            semaphore = threading.BoundedSemaphore(1)
            tasks = TaskManager(root / 'tasks', semaphore)
            http = server.LocalServer(('127.0.0.1', 0), partial(server.Handler, directory='web'))
            thread = threading.Thread(target=http.serve_forever, daemon=True)
            thread.start()
            a, b, pairs, _ = fixture()
            request = root / 'request.json'
            request.write_text(json.dumps(dict(source=a, target=b, pairs=pairs, iterations=5)), encoding='utf-8')
            (root / 'source.obj').write_text(a, encoding='utf-8')
            (root / 'target.obj').write_text(b, encoding='utf-8')
            (root / 'constraints.json').write_text(json.dumps(dict(pairs=pairs, iterations=5)), encoding='utf-8')

            async def exercise():
                params = StdioServerParameters(command=sys.executable, args=['mcp_server.py', '--api-url',
                    'http://127.0.0.1:' + str(http.server_address[1])], cwd=str(Path(__file__).resolve().parents[1]))
                async with stdio_client(params) as (reader, writer):
                    async with ClientSession(reader, writer) as session:
                        await session.initialize()
                        self.assertEqual(len((await session.list_tools()).tools), 7)
                        async def call(name, arguments):
                            response = await session.call_tool(name, arguments)
                            self.assertFalse(response.isError, response)
                            return json.loads(response.content[0].text)
                        self.assertEqual((await call('service_health', {}))['app'], 'Mesh Wave')
                        task = await call('submit_fit', {'request_path': str(root / 'constraints.json'),
                            'source_path': str(root / 'source.obj'), 'target_path': str(root / 'target.obj')})
                        for _ in range(100):
                            job = await call('get_task', {'task_id': task['id']})
                            if job['status'] in ('completed', 'failed'):
                                break
                            await asyncio.sleep(.1)
                        self.assertEqual(job['status'], 'completed', job)
                        await call('save_preview', {'task_id': task['id'], 'output_path': str(root / 'preview.json')})
                        await call('export_result', {'task_id': task['id'], 'output_path': str(root / 'result.obj')})
                        self.assertIn('f ', (root / 'result.obj').read_text())
                        duplicate = await session.call_tool('export_result', {'task_id': task['id'], 'output_path': str(root / 'result.obj')})
                        self.assertTrue(duplicate.isError)
                        self.assertTrue((await call('list_tasks', {}))['tasks'])
                        semaphore.acquire()
                        try:
                            task = await call('submit_fit', {'request_path': str(request)})
                            self.assertEqual((await call('cancel_task', {'task_id': task['id']}))['status'], 'cancelled')
                        finally:
                            semaphore.release()
            try:
                with patch.object(server, 'TASKS', tasks):
                    asyncio.run(exercise())
            finally:
                tasks.close()
                http.shutdown()
                http.server_close()
                thread.join(5)


if __name__ == '__main__':
    unittest.main()
