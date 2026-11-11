import unittest
import numpy as np
from scipy import sparse
from local_guard import local_safe_solve
from surface import FlipGuard

class LocalGuardTests(unittest.TestCase):
    def mesh(self):
        v=np.array([[0.,0,0],[1,0,0],[0,1,0],[3,0,0],[4,0,0],[3,1,0]])
        return v,np.array([[0,1,2],[3,4,5]])

    def test_unsafe_patch_freezes_locally_while_other_patch_reaches_target(self):
        v,f=self.mesh();desired=np.zeros_like(v);desired[2,1]=-100;desired[3:,2]=.2
        guard=FlipGuard(v,f);self.assertLess(guard.safe_step(v,v+desired),.125)
        frozen=np.zeros(6,bool)
        result,scale,faces,rounds=local_safe_solve(sparse.eye(6,format='csc'),desired,sparse.csr_matrix((0,6)),np.empty((0,3)),sparse.eye(6,format='csr'),v,np.zeros_like(v),np.zeros_like(v),frozen,guard)
        np.testing.assert_array_equal(result[:3],0);np.testing.assert_allclose(result[3:,2],.2)
        self.assertEqual(scale,1);self.assertEqual(faces,{0});self.assertEqual(rounds,1)
        np.testing.assert_array_equal(frozen,[1,1,1,0,0,0]);self.assertGreaterEqual(guard.minimum_ratio(v+result),.01)

    def test_barycentric_equality_survives_local_freeze_and_resolve(self):
        v,f=self.mesh();coeff=np.zeros_like(v);coeff[3,2]=.1
        c=sparse.csr_matrix([[.5,0,0,.5,0,0]]);values=c@coeff
        rhs=np.zeros_like(v);rhs[2,1]=-100;rhs[3:,2]=.2
        result,scale,_,_=local_safe_solve(sparse.eye(6,format='csc'),rhs,c,values,sparse.eye(6,format='csr'),v,np.zeros_like(v),coeff,np.zeros(6,bool),FlipGuard(v,f))
        np.testing.assert_allclose(c@result,values,atol=1e-12)
        self.assertAlmostEqual(result[3,2],.1);self.assertAlmostEqual(result[4,2],.2);self.assertEqual(scale,1)

    def test_reduced_basis_protects_only_controls_touching_dangerous_face(self):
        v,f=self.mesh();basis=sparse.csr_matrix(([1]*6,([0,1,2,3,4,5],[0,1,2,3,3,3])),shape=(6,4))
        rhs=np.zeros((4,3));rhs[2,1]=-100;rhs[3,2]=.2;frozen=np.zeros(4,bool)
        result,scale,faces,_=local_safe_solve(sparse.eye(4,format='csc'),rhs,sparse.csr_matrix((0,4)),np.empty((0,3)),basis,v,np.zeros_like(v),np.zeros((4,3)),frozen,FlipGuard(v,f))
        np.testing.assert_array_equal(frozen,[1,1,1,0]);self.assertEqual(faces,{0});self.assertEqual(scale,1)
        np.testing.assert_allclose((basis@result)[3:,2],.2)

    def test_continuous_path_detects_collapse_hidden_by_positive_endpoint(self):
        v,f=self.mesh();proposal=v.copy();proposal[1]=[-1,0,0];proposal[2]=[0,-1,0]
        guard=FlipGuard(v,f);self.assertGreater(guard.minimum_ratio(proposal),.99)
        np.testing.assert_array_equal(guard.limiting_faces(v,proposal,1),[0])
        self.assertLess(guard.safe_step(v,proposal),.5)

    def test_all_controls_blocked_returns_no_step_without_weakening_guard(self):
        v,f=self.mesh();v=v[:3];f=f[:1];rhs=np.zeros_like(v);rhs[2,1]=-100
        frozen=np.zeros(3,bool);result,scale,faces,_=local_safe_solve(sparse.eye(3,format='csc'),rhs,sparse.csr_matrix((0,3)),np.empty((0,3)),sparse.eye(3,format='csr'),v,np.zeros_like(v),np.zeros_like(v),frozen,FlipGuard(v,f))
        self.assertEqual(scale,0);self.assertEqual(faces,{0});np.testing.assert_array_equal(result,0)

if __name__=='__main__':unittest.main()
