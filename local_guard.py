"""Restrict unsafe local deformation controls, then re-solve the remaining mesh.

Frozen controls retain their current feasible values for this stage. Hard point
equalities remain in every reduced solve; the original continuous-path guard
still checks the whole mesh before any update is accepted.
"""
import numpy as np
from point_constraints import solve_affine


def local_safe_solve(matrix, rhs, equality, values, basis, base, anchor,
                     coefficients, frozen, guard, max_rounds=12):
    current = base + anchor + basis @ coefficients
    protected_faces = set()
    rounds = 0
    for iteration in range(max_rounds + 1):
        free = np.flatnonzero(~frozen)
        fixed = np.flatnonzero(frozen)
        if not len(free):
            return coefficients.copy(), 0., protected_faces, rounds
        proposal = coefficients.copy()
        adjusted_rhs = rhs[free] - matrix[free][:, fixed] @ coefficients[fixed]
        adjusted_values = values - equality[:, fixed] @ coefficients[fixed]
        proposal[free] = solve_affine(matrix[free][:, free].tocsc(), adjusted_rhs,
                                      equality[:, free], adjusted_values)
        if not np.isfinite(proposal).all():
            raise ValueError('求解失败；请检查模型和对应点。')
        candidate = base + anchor + basis @ proposal
        scale = guard.safe_step(current, candidate)
        if scale >= .125 or iteration == max_rounds:
            return proposal, scale, protected_faces, rounds
        faces = guard.limiting_faces(current, candidate, .125)
        vertices = np.unique(guard.faces[faces])
        controls = np.unique(basis[vertices].indices)
        newly_frozen = controls[~frozen[controls]]
        if not len(newly_frozen):
            return proposal, scale, protected_faces, rounds
        frozen[newly_frozen] = True
        protected_faces.update(int(i) for i in faces)
        rounds += 1
