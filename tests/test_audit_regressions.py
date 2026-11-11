import unittest
import numpy as np
from scipy import sparse
from point_constraints import solve_affine
from wrap_core import export_obj,parse_obj

class AuditRegressionTests(unittest.TestCase):
    def test_close_independent_surface_constraints_are_not_discarded(self):
        c=sparse.csr_matrix([[.5,.5,0],[.500001,.499999,0],[0,0,1.]])
        expected=np.array([[0.,0,0],[1,0,0],[0,1,0]])
        result=solve_affine(sparse.eye(3),np.zeros((3,3)),c,c@expected)
        np.testing.assert_allclose(c@result,c@expected,atol=1e-9)
        np.testing.assert_allclose(result,expected,atol=1e-4)

    def test_export_keeps_float_precision_at_large_world_offsets(self):
        text='v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n'
        coordinates=np.array([[1e9+.012345678,2e8+.1,-3e7+.01],[1e9+.2,2e8+.1,-3e7+.01],[1e9+.012345678,2e8+.3,-3e7+.01]])
        actual,faces=parse_obj(export_obj(text,coordinates))
        np.testing.assert_array_equal(actual,coordinates)
        self.assertGreater(np.linalg.norm(np.cross(actual[1]-actual[0],actual[2]-actual[0])),.01)

    def test_solver_timing_includes_final_quality_queries(self):
        from unittest.mock import patch
        from test_surface_constraints import grid,obj
        from surface import TriangleSurface
        from wrap_core import wrap
        v,f,t,p=grid();clock=[0.];query=TriangleSurface.query
        def measured(*args,**kwargs):
            clock[0]+=1
            return query(*args,**kwargs)
        with patch('surface_wrap.perf_counter',side_effect=lambda:clock[0]),patch.object(TriangleSurface,'query',measured):
            result=wrap(obj(v,f),obj(t,f),p,5)
        self.assertEqual(result['stats']['totalSeconds'],clock[0])

    def test_failed_worker_start_is_persisted_and_unlocks_solver(self):
        import tempfile,threading
        from pathlib import Path
        from unittest.mock import patch
        from batch_jobs import BatchManager
        from test_core import fixture
        a,b,p,_=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            gate=threading.BoundedSemaphore(1);manager=BatchManager(Path(tmp),gate)
            job=manager.create({'mode':'sequence','source':{'name':'template.obj','text':a},'referenceTarget':b,'pairs':p})
            manager.add({'jobId':job['id'],'name':'scan.obj','text':b})
            with patch('threading.Thread.start',side_effect=RuntimeError('worker unavailable')):
                with self.assertRaises(RuntimeError):manager.start(job['id'])
            restored=BatchManager(Path(tmp),threading.BoundedSemaphore(1)).status(job['id'])
            self.assertNotIn(job['id'],manager.threads)
            self.assertEqual(restored['status'],'failed')
            self.assertEqual(restored['counts']['skipped'],1)
            self.assertTrue(restored['archiveReady'])
            self.assertTrue(gate.acquire(False));gate.release()

if __name__=='__main__':unittest.main()
