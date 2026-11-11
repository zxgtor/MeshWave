"""Read-only, per-vertex distances to the retained continuous target surface."""
import numpy as np
from surface import TriangleSurface, face_vectors, vertex_normals
from wrap_core import parse_obj, exclusion_masks, MAX_SOURCE


def inspect_fit(body):
    source, faces = parse_obj(body['source'])
    target, target_faces = parse_obj(body['target'])
    vertices = np.asarray(body['vertices'], dtype=float)
    if len(source) > MAX_SOURCE or vertices.shape != source.shape or not np.isfinite(vertices).all():
        raise ValueError('质量检查的结果顶点无效或模板过大。')
    angle = body.get('normalAngle', 60)
    if type(angle) not in (int, float) or not np.isfinite(angle) or not 10 <= angle <= 89:
        raise ValueError('法线夹角必须为 10–89 度。')
    masks = exclusion_masks(faces, target_faces, body.get('excludedFaces', {}), [])
    retained = np.delete(target_faces, masks['target'][0], axis=0)
    unit = float(np.linalg.norm(np.ptp(target, axis=0)))
    if not np.isfinite(unit) or unit <= 0:
        raise ValueError('扫描模型尺寸无效。')
    # Normalization keeps triangle queries independent of arbitrary OBJ units.
    origin = target.min(axis=0)
    target_normalized = (target - origin) / unit
    current = (vertices - origin) / unit
    if not np.isfinite(current).all():
        raise ValueError('质量检查的结果顶点无效或模板过大。')
    surface = TriangleSurface(target_normalized, retained)
    active = np.zeros(len(source), dtype=bool)
    active[np.unique(faces)] = True
    active[masks['source'][1]] = False
    ids = np.flatnonzero(active)
    distances = [None] * len(source)
    angles = [None] * len(source)
    if len(ids):
        _, distance, nearest = surface.query(current[ids])
        distance *= unit
        if not np.isfinite(distance).all():
            raise ValueError('质量检查的表面距离无效。')
        normals = vertex_normals(current, faces)[ids]
        target_normals = face_vectors(target_normalized, retained[nearest])
        target_normals /= np.linalg.norm(target_normals, axis=1)[:, None]
        dots = np.clip(np.sum(normals * target_normals, axis=1), -1, 1)
        degrees = np.degrees(np.arccos(dots))
        valid_normal = np.linalg.norm(normals, axis=1) > .5
        for row, vertex in enumerate(ids):
            distances[int(vertex)] = float(distance[row])
            if valid_normal[row]:
                angles[int(vertex)] = float(degrees[row])
    return {'distances': distances, 'normalAngles': angles, 'unit': unit,
            'normalAngle': angle, 'excludedVertices': int((~active).sum()),
            'excludedTargetFaces': len(masks['target'][0]),
            'ignoredDegenerateTargetFaces': surface.ignored_degenerate}
