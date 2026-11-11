"""Single-image OBJ albedo preview, UV baking, and portable texture export."""
import base64
import io
import zipfile
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from scipy.ndimage import distance_transform_edt
from surface import TriangleSurface, vertex_normals
from wrap_core import parse_obj, export_obj, index_list, MAX_SOURCE

INPUT_BYTES = 8 * 1024 * 1024
BAKED_BYTES = 20 * 1024 * 1024


def png_texture(image, name, limit=INPUT_BYTES):
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    raw = buffer.getvalue()
    if len(raw) > limit:
        raise ValueError('PNG 贴图超过允许大小，请降低图片分辨率。')
    return {'name': name[:500], 'dataUrl': 'data:image/png;base64,' + base64.b64encode(raw).decode('ascii'),
            'width': image.width, 'height': image.height}


def read_texture(value, limit=INPUT_BYTES):
    if not isinstance(value, dict) or not isinstance(value.get('dataUrl'), str) or not isinstance(value.get('name'), str):
        raise ValueError('贴图名称或内容无效。')
    url = value['dataUrl']
    if len(url) > (limit * 4 // 3 + 200) or ',' not in url:
        raise ValueError('贴图超过大小限制。')
    header, encoded = url.split(',', 1)
    if header not in ('data:image/png;base64', 'data:image/jpeg;base64'):
        raise ValueError('仅支持 PNG 或 JPEG 贴图。')
    try:
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > limit:
            raise ValueError('贴图超过大小限制。')
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('PNG', 'JPEG') or image.width * image.height > 16 * 1024 * 1024:
                raise ValueError('贴图只支持 PNG/JPEG，最多 16 百万像素。')
            return ImageOps.exif_transpose(image).convert('RGBA')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('贴图文件损坏或无法读取。') from exc


def normalize_texture(value, baked=False):
    limit = BAKED_BYTES if baked else INPUT_BYTES
    return png_texture(read_texture(value, limit), value['name'], limit)


def rasterize_uv(uv, uv_faces, resolution):
    if not len(uv) or np.any(uv_faces < 0):
        raise ValueError('模板需要每个面角都有有效 UV。')
    if np.any(uv < 0) or np.any(uv > 1):
        raise ValueError('模板 UV 需位于单张 0–1 空间；暂不支持 UDIM。')
    face_map = np.full((resolution, resolution), -1, dtype=np.int32)
    bary = np.zeros((resolution, resolution, 2), dtype=np.float32)
    skipped, work = 0, 0
    for face_id, indices in enumerate(uv_faces):
        tri = uv[indices] * [resolution, -resolution] + [-.5, resolution - .5]
        a, b, c = tri
        edge1, edge2 = b - a, c - a
        determinant = edge1[0] * edge2[1] - edge1[1] * edge2[0]
        if abs(determinant) < 1e-10:
            skipped += 1
            continue
        lo = np.maximum(np.ceil(tri.min(0)).astype(int), 0)
        hi = np.minimum(np.floor(tri.max(0)).astype(int), resolution - 1)
        if np.any(hi < lo):
            continue
        work += int(np.prod(hi - lo + 1))
        if work > 80000000:
            raise ValueError('UV 布局的栅格化开销过高，请降低分辨率或整理 UV。')
        x, y = np.meshgrid(np.arange(lo[0], hi[0] + 1), np.arange(lo[1], hi[1] + 1))
        dx, dy = x - a[0], y - a[1]
        u = (dx * edge2[1] - dy * edge2[0]) / determinant
        v = (edge1[0] * dy - edge1[1] * dx) / determinant
        inside = (u >= -1e-8) & (v >= -1e-8) & (u + v <= 1 + 1e-8)
        x, y, u, v = x[inside], y[inside], u[inside], v[inside]
        existing = face_map[y, x] >= 0
        old = bary[y, x]
        old_inside = (old[:, 0] > 1e-6) & (old[:, 1] > 1e-6) & (old.sum(1) < 1 - 1e-6)
        new_inside = (u > 1e-6) & (v > 1e-6) & (u + v < 1 - 1e-6)
        if np.any(existing & old_inside & new_inside):
            raise ValueError('模板 UV 存在重叠像素，请先展开为不重叠的单张 UV。')
        keep = ~existing
        face_map[y[keep], x[keep]] = face_id
        bary[y[keep], x[keep], 0] = u[keep]
        bary[y[keep], x[keep], 1] = v[keep]
    return face_map, bary, skipped


def prepare_image(image):
    rgba = np.asarray(image, dtype=np.float32) / 255
    rgb = np.where(rgba[..., :3] <= .04045, rgba[..., :3] / 12.92, ((rgba[..., :3] + .055) / 1.055) ** 2.4)
    rgba[..., :3] = rgb * rgba[..., 3:]
    return rgba


def sample_image(image, uv):
    """Bilinear repeat sampling; OBJ v=0 is the image bottom. Blend linear premultiplied RGBA."""
    rgba = prepare_image(image) if isinstance(image, Image.Image) else image
    height, width = rgba.shape[:2]
    uv = np.remainder(uv, 1)
    x, y = uv[:, 0] * width - .5, (1 - uv[:, 1]) * height - .5
    ix, iy = np.floor(x).astype(int), np.floor(y).astype(int)
    tx, ty = (x - ix)[:, None], (y - iy)[:, None]
    result = ((1-tx)*(1-ty)*rgba[iy % height, ix % width] + tx*(1-ty)*rgba[iy % height, (ix+1) % width]
              + (1-tx)*ty*rgba[(iy+1) % height, ix % width] + tx*ty*rgba[(iy+1) % height, (ix+1) % width])
    rgb = np.divide(result[:, :3], result[:, 3:], out=np.zeros_like(result[:, :3]), where=result[:, 3:] > 1e-8)
    result[:, :3] = np.where(rgb <= .0031308, rgb * 12.92, 1.055 * np.maximum(rgb, 0) ** (1/2.4) - .055)
    return np.rint(np.clip(result, 0, 1) * 255).astype(np.uint8)


def bake_texture(source_text, target_text, vertices, target_texture, resolution=1024, padding=8,
                 distance_ratio=.02, normal_angle=60, excluded_faces=None):
    source, source_faces, source_uv, source_uf = parse_obj(source_text, with_uv=True)
    target, target_faces, target_uv, target_uf = parse_obj(target_text, with_uv=True)
    wrapped = np.asarray(vertices, dtype=float)
    if len(source) > MAX_SOURCE or wrapped.shape != source.shape or not np.isfinite(wrapped).all():
        raise ValueError('贴合结果顶点无效或模板过大。')
    if type(resolution) is not int or resolution not in (256, 512, 1024, 2048):
        raise ValueError('贴图分辨率仅支持 256、512、1024、2048。')
    if type(padding) is not int or not 0 <= padding <= 16:
        raise ValueError('边缘扩展范围为 0–16 像素。')
    if type(distance_ratio) not in (float, int) or not np.isfinite(distance_ratio) or not .001 <= distance_ratio <= .2:
        raise ValueError('最大投射距离需为目标包围盒对角线的 0.1%–20%。')
    if type(normal_angle) not in (float, int) or not np.isfinite(normal_angle) or not 10 <= normal_angle <= 89:
        raise ValueError('法线夹角必须为 10–89 度。')
    if not len(target_uv) or np.any(target_uf < 0):
        raise ValueError('扫描模型需要每个面角都有有效 UV。')
    masks = {} if excluded_faces is None else excluded_faces
    if not isinstance(masks, dict):
        raise ValueError('排除区域格式无效。')
    excluded_source = index_list(masks.get('source', []), len(source_faces), '模板排除面')
    excluded_target = index_list(masks.get('target', []), len(target_faces), '目标排除面')
    if len(excluded_target) == len(target_faces):
        raise ValueError('不能排除全部目标面。')
    image = read_texture(target_texture)
    pixels = prepare_image(image)
    unit = float(np.linalg.norm(np.ptp(target, axis=0)))
    if not np.isfinite(unit) or unit < 1e-12:
        raise ValueError('扫描模型尺寸无效。')
    center = target.mean(0)
    fixed, floating = (target-center)/unit, (wrapped-center)/unit
    allowed = np.delete(np.arange(len(target_faces)), excluded_target)
    surface = TriangleSurface(fixed, target_faces[allowed])
    face_map, bary, degenerate_uv = rasterize_uv(source_uv, source_uf, resolution)
    occupied = face_map >= 0
    enabled = occupied & ~np.isin(face_map, excluded_source)
    ys, xs = np.nonzero(enabled)
    if not len(xs):
        raise ValueError('模板没有可烘焙的 UV 像素，请检查 UV、排除区域或分辨率。')
    output = np.zeros((resolution, resolution, 4), dtype=np.uint8)
    valid_map = np.zeros((resolution, resolution), dtype=bool)
    normals = vertex_normals(floating, source_faces)
    matched = 0
    for offset in range(0, len(xs), 4096):
        x, y = xs[offset:offset+4096], ys[offset:offset+4096]
        ids = source_faces[face_map[y, x]]
        uv = bary[y, x].astype(float)
        weights = np.column_stack([1-uv.sum(1), uv])
        points = np.sum(floating[ids] * weights[..., None], axis=1)
        sn = np.sum(normals[ids] * weights[..., None], axis=1)
        sn /= np.maximum(np.linalg.norm(sn, axis=1)[:, None], 1e-30)
        closest, distances, face = surface.query(points, sn, float(np.cos(np.deg2rad(normal_angle))))
        valid = np.isfinite(distances) & (distances <= distance_ratio)
        if not valid.any():
            continue
        x, y = x[valid], y[valid]
        target_ids = allowed[face[valid]]
        tri = fixed[target_faces[target_ids]]
        ab, ac, ap = tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0], closest[valid]-tri[:, 0]
        normal = np.cross(ab, ac); norm2 = np.sum(normal*normal, axis=1)
        u = np.sum(np.cross(ap, ac)*normal, axis=1)/norm2
        v = np.sum(np.cross(ab, ap)*normal, axis=1)/norm2
        target_weights = np.column_stack([1-u-v, u, v])
        coordinates = np.sum(target_uv[target_uf[target_ids]] * target_weights[..., None], axis=1)
        output[y, x] = sample_image(pixels, coordinates)
        valid_map[y, x] = True
        matched += len(x)
    if not matched:
        raise ValueError('没有像素通过投射距离和法线检查，请检查贴合结果、面朝向或增大投射距离。')
    if padding:
        distance, nearest = distance_transform_edt(~valid_map, return_indices=True)
        grow = (~occupied) & (distance <= padding)
        output[grow] = output[nearest[0][grow], nearest[1][grow]]
    return {'texture': png_texture(Image.fromarray(output), 'baked.png', BAKED_BYTES), 'stats': {
        'resolution': resolution, 'atlasPixels': int(occupied.sum()), 'eligiblePixels': len(xs),
        'matchedPixels': matched, 'unmatchedPixels': len(xs)-matched,
        'coverage': matched/len(xs), 'padding': padding, 'degenerateUVFaces': degenerate_uv,
        'maxDistance': distance_ratio*unit, 'normalAngle': normal_angle}}


def texture_bundle(source_text, vertices, texture):
    _, _, uv, uf = parse_obj(source_text, with_uv=True)
    if not len(uv) or np.any(uf < 0):
        raise ValueError('纹理模型导出需要完整 UV。')
    image = read_texture(texture, BAKED_BYTES)
    geometry = export_obj(source_text, vertices)
    lines = [line for line in geometry.splitlines() if not line.split() or line.split()[0] not in ('mtllib', 'usemtl')]
    geometry = 'mtllib model.mtl\nusemtl baked\n' + '\n'.join(lines) + '\n'
    png = io.BytesIO(); image.save(png, format='PNG')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('model.obj', geometry)
        archive.writestr('model.mtl', 'newmtl baked\nKa 0 0 0\nKd 1 1 1\nKs 0 0 0\nd 1\nillum 1\nmap_Kd texture.png\nmap_d opacity.png\n')
        archive.writestr('texture.png', png.getvalue())
        opacity = io.BytesIO(); image.getchannel('A').save(opacity, format='PNG')
        archive.writestr('opacity.png', opacity.getvalue())
    return buffer.getvalue()
