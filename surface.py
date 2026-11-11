"""Exact floating-point triangle queries and conservative local orientation guard."""
import numpy as np
from scipy.spatial import cKDTree


def face_vectors(vertices, faces):
    tri = vertices[faces]
    return np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])


def vertex_normals(vertices, faces):
    normals = np.zeros_like(vertices)
    vectors = face_vectors(vertices, faces)
    for column in range(3):
        np.add.at(normals, faces[:, column], vectors)
    length = np.linalg.norm(normals, axis=1)
    return normals / np.maximum(length[:, None], 1e-30)


def closest_triangle_points(points, triangles):
    """Broadcast (...,3) points against (...,3,3) nondegenerate triangles.

    The minimum is either the perpendicular projection inside the triangle,
    or a clamped projection onto one of its three edges (including endpoints).
    """
    a, b, c = triangles[..., 0, :], triangles[..., 1, :], triangles[..., 2, :]
    ab, ac, ap = b - a, c - a, points - a
    normal = np.cross(ab, ac)
    norm2 = np.sum(normal * normal, axis=-1)
    u = np.sum(np.cross(ap, ac) * normal, axis=-1) / np.maximum(norm2, 1e-300)
    v = np.sum(np.cross(ab, ap) * normal, axis=-1) / np.maximum(norm2, 1e-300)
    projection = a + u[..., None] * ab + v[..., None] * ac
    inside = (u >= 0) & (v >= 0) & (u + v <= 1)
    candidates = [projection]
    for start, end in [(a, b), (b, c), (c, a)]:
        edge = end - start
        t = np.sum((points - start) * edge, axis=-1) / np.maximum(np.sum(edge * edge, axis=-1), 1e-300)
        candidates.append(start + np.clip(t, 0, 1)[..., None] * edge)
    candidates = np.stack(candidates, axis=-2)
    distance2 = np.sum((candidates - points[..., None, :]) ** 2, axis=-1)
    distance2[..., 0] = np.where(inside, distance2[..., 0], np.inf)
    best = np.argmin(distance2, axis=-1)
    return np.take_along_axis(candidates, best[..., None, None], axis=-2)[..., 0, :]


class TriangleSurface:
    """AABB BVH with proven lower-bound pruning, not a fixed-k centroid heuristic.

    Normal filtering finds the nearest *eligible* triangle, including ones farther
    than the geometric nearest. Face-normal component bounds safely prune nodes.
    """
    def __init__(self, vertices, faces, leaf_size=16):
        all_tri = vertices[faces]
        vectors = face_vectors(vertices, faces)
        lengths = np.linalg.norm(vectors, axis=1)
        valid = lengths > 1e-14
        self.ignored_degenerate = int(np.sum(~valid))
        if not valid.any():
            raise ValueError('目标参与贴合的区域没有有效三角面。')
        self.face_ids = np.flatnonzero(valid)
        self.triangles = all_tri[valid]
        self.normals = vectors[valid] / lengths[valid, None]
        self.face_normals = vectors / np.maximum(lengths[:, None], 1e-30)
        self.centers = self.triangles.mean(axis=1)
        self.seed_tree = cKDTree(self.centers)
        self.nodes = []

        def build(ids):
            triangles = self.triangles[ids]
            node = {'lo': triangles.min(axis=(0, 1)), 'hi': triangles.max(axis=(0, 1)),
                    'nlo': self.normals[ids].min(axis=0), 'nhi': self.normals[ids].max(axis=0)}
            index = len(self.nodes)
            self.nodes.append(node)
            if len(ids) <= leaf_size:
                node['ids'] = ids
            else:
                axis = int(np.argmax(np.ptp(self.centers[ids], axis=0)))
                order = ids[np.argpartition(self.centers[ids, axis], len(ids) // 2)]
                half = len(ids) // 2
                node['children'] = (build(order[:half]), build(order[half:]))
            return index
        build(np.arange(len(self.triangles)))

    def query(self, points, normals=None, cosine=0.5):
        points = np.asarray(points, dtype=float)
        all_closest = np.zeros_like(points)
        all_distance = np.full(len(points), np.inf)
        all_faces = np.full(len(points), -1, dtype=int)
        for offset in range(0, len(points), 512):
            p = points[offset:offset + 512]
            sn = None if normals is None else normals[offset:offset + 512]
            seed = self.seed_tree.query(p)[1]
            closest = closest_triangle_points(p, self.triangles[seed])
            best = np.sum((closest - p) ** 2, axis=1)
            face = seed.copy()
            if sn is not None:
                eligible = np.sum(sn * self.normals[seed], axis=1) >= cosine
                best[~eligible] = np.inf
                face[~eligible] = -1
            stack = [(0, np.arange(len(p)))]
            while stack:
                node_id, candidates = stack.pop()
                node = self.nodes[node_id]
                delta = np.maximum(np.maximum(node['lo'] - p[candidates], p[candidates] - node['hi']), 0)
                keep = np.sum(delta * delta, axis=1) <= best[candidates] + 1e-14 * np.maximum(1, best[candidates])
                if sn is not None:
                    bound = np.sum(sn[candidates] * np.where(sn[candidates] >= 0, node['nhi'], node['nlo']), axis=1)
                    keep &= bound >= cosine - 1e-14
                candidates = candidates[keep]
                if not len(candidates):
                    continue
                if 'children' in node:
                    stack.extend((child, candidates) for child in node['children'])
                    continue
                ids = node['ids']
                q = closest_triangle_points(p[candidates, None, :], self.triangles[ids][None, :])
                d2 = np.sum((q - p[candidates, None, :]) ** 2, axis=2)
                if sn is not None:
                    eligible = sn[candidates] @ self.normals[ids].T >= cosine
                    d2[~eligible] = np.inf
                col = np.argmin(d2, axis=1)
                distance = d2[np.arange(len(col)), col]
                improved = distance < best[candidates]
                rows, chosen = candidates[improved], col[improved]
                best[rows] = distance[improved]
                closest[rows] = q[improved, chosen]
                face[rows] = ids[chosen]
            all_closest[offset:offset + len(p)] = closest
            all_distance[offset:offset + len(p)] = np.sqrt(best)
            valid = face >= 0
            output_faces = np.full(len(p), -1, dtype=int)
            output_faces[valid] = self.face_ids[face[valid]]
            all_faces[offset:offset + len(p)] = output_faces
        return all_closest, all_distance, all_faces


class FlipGuard:
    """Keep signed projected area >=1% of the aligned reference throughout a step.

    This conservative local guard limits rotation relative to the reference;
    it does not claim to detect global self-intersection of distant triangles.
    """
    def __init__(self, reference, faces, min_ratio=.01):
        self.faces = faces
        cross = face_vectors(reference, faces)
        self.area = np.linalg.norm(cross, axis=1)
        if np.any(self.area <= 1e-14):
            raise ValueError('模板包含零面积或过小三角面，请先清理模型。')
        self.normal = cross / self.area[:, None]
        self.min_ratio = min_ratio

    def minimum_ratio(self, vertices):
        return float(np.min(np.sum(face_vectors(vertices, self.faces) * self.normal, axis=1) / self.area))

    def safe_step(self, current, proposal):
        tri, delta = current[self.faces], (proposal - current)[self.faces]
        e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
        d1, d2 = delta[:, 1] - delta[:, 0], delta[:, 2] - delta[:, 0]
        a = np.sum(np.cross(d1, d2) * self.normal, axis=1) / self.area
        b = np.sum((np.cross(d1, e2) + np.cross(e1, d2)) * self.normal, axis=1) / self.area
        c = np.sum(np.cross(e1, e2) * self.normal, axis=1) / self.area
        alpha = 1.
        for _ in range(22):
            minimum = np.minimum(c, a * alpha * alpha + b * alpha + c)
            convex = a > 1e-30
            t = np.zeros_like(a)
            t[convex] = np.clip(-b[convex] / (2 * a[convex]), 0, alpha)
            minimum[convex] = np.minimum(minimum[convex], (a * t * t + b * t + c)[convex])
            if np.all(minimum >= self.min_ratio):
                return alpha
            alpha *= .5
        return 0.
