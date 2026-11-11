"""Read-only OBJ diagnosis and explicit topology-changing repair previews."""
from collections import defaultdict, deque
import numpy as np
from wrap_core import mesh_data, MAX_SOURCE


def read_mesh(text):
    if not isinstance(text,str) or len(text.encode('utf-8'))>18*1024*1024:
        raise ValueError('诊断 OBJ 文件上限为 18 MB。')
    vertices,extras,uvs,polygons,headers=[],[],[],[],[]
    tags={};details=[]
    for number,line in enumerate(text.splitlines(),1):
        p=line.split('#',1)[0].split()
        if not p:continue
        if p[0] in ('v','vt'):
            size=3 if p[0]=='v' else 2
            try:
                value=[float(x) for x in p[1:1+size]]
                if len(value)!=size or not np.isfinite(value).all():raise ValueError()
            except ValueError:
                value=None;details.append({'line':number,'reason':'无效顶点' if p[0]=='v' else '无效 UV'})
            if p[0]=='v':vertices.append(value);extras.append(p[4:])
            else:uvs.append(value)
        elif p[0]=='f':
            corners=[];bad=False
            for token in p[1:]:
                try:
                    fields=token.split('/');v=int(fields[0]);u=None
                    if v==0:raise ValueError()
                    v=v-1 if v>0 else len(vertices)+v
                    if len(fields)>1 and fields[1]:
                        try:
                            u=int(fields[1]);u=u-1 if u>0 else len(uvs)+u if u<0 else -1
                        except ValueError:u=-1
                    corners.append((v,u))
                except ValueError:bad=True
            polygons.append({'corners':corners,'bad':bad or len(corners)<3,'line':number,'tags':list(tags.values())})
        elif p[0]=='mtllib':headers.append(' '.join(p))
        elif p[0] in ('usemtl','g','o','s'):tags[p[0]]=' '.join(p)
    if len(vertices)>200000 or sum(max(1,len(p['corners'])-2) for p in polygons)>500000:
        raise ValueError('诊断上限为 200,000 顶点、500,000 三角面。')
    finite=[v for v in vertices if v is not None]
    if not finite:raise ValueError('文件没有可显示的有限坐标顶点。')
    unit=max(float(np.linalg.norm(np.ptp(finite,axis=0))),1e-30)
    if not np.isfinite(unit):raise ValueError('模型坐标跨度过大，请归一化后重试。')
    faces=[];invalid_lines=set();duplicate=0;bad_uv=0;seen=set();invalid_segments=[];invalid_points=[]
    for polygon in polygons:
        start_uv=bad_uv
        c=polygon['corners'];valid_ids=[v for v,_ in c if 0<=v<len(vertices) and vertices[v] is not None]
        invalid=polygon['bad'] or len(valid_ids)!=len(c)
        triangles=[]
        if not invalid:
            for j in range(1,len(c)-1):
                tri=[c[0],c[j],c[j+1]];ids=[v for v,_ in tri]
                a,b,d=(np.array(vertices[i]) for i in ids)
                edge_scale=max(float(np.max(np.abs(b-a))),float(np.max(np.abs(d-a))),float(np.max(np.abs(d-b))))
                if len(set(ids))<3 or edge_scale==0 or np.linalg.norm(np.cross((b-a)/edge_scale,(d-a)/edge_scale))<=1e-14:
                    invalid=True;continue
                key=tuple(sorted(ids))
                if key in seen:duplicate+=1;invalid=True;continue
                seen.add(key);uv=[]
                for _,u in tri:
                    if u is not None and (u<0 or u>=len(uvs) or uvs[u] is None):bad_uv+=1;u=None
                    uv.append(u)
                triangles.append({'v':ids,'uv':uv,'tags':polygon['tags']})
        faces.extend(triangles)
        if invalid:
            invalid_lines.add(polygon['line']);details.append({'line':polygon['line'],'reason':'无效或重复面'})
        if bad_uv>start_uv:details.append({'line':polygon['line'],'reason':'无效 UV 引用；修复时保留几何'})
        if invalid or bad_uv>start_uv:
            positions=[vertices[i] for i in valid_ids];invalid_points.extend(positions)
            if len(positions)>1:
                for a,b in zip(positions,positions[1:]+positions[:1]):invalid_segments.extend([a,b])
    return {'vertices':vertices,'extras':extras,'uvs':uvs,'faces':faces,'headers':headers,'details':details,
            'invalidFaces':len(invalid_lines),'duplicateFaces':duplicate,'invalidUVs':bad_uv+sum(u is None for u in uvs),
            'invalidSegments':invalid_segments,'invalidPoints':invalid_points}


def topology(faces,vertex_count):
    edges=defaultdict(list);incident=defaultdict(list)
    for i,face in enumerate(faces):
        v=face['v']
        for x in v:incident[x].append(i)
        for a,b in zip(v,v[1:]+v[:1]):edges[tuple(sorted((a,b)))].append((i,a<b))
    parent=list(range(len(faces)*3))
    def root(x):
        while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
        return x
    def union(a,b):parent[root(a)]=root(b)
    for edge,rows in edges.items():
        if len(rows)==2:
            a,b=rows[0][0],rows[1][0]
            for v in edge:union(a*3+faces[a]['v'].index(v),b*3+faces[b]['v'].index(v))
    fans={v:{root(i*3+faces[i]['v'].index(v)) for i in ids} for v,ids in incident.items()}
    return edges,incident,fans,root


def report_mesh(mesh):
    vertices=mesh['vertices'];faces=mesh['faces'];edges,incident,fans,_=topology(faces,len(vertices))
    nonmanifold=[edge for edge,rows in edges.items() if len(rows)>2]
    winding=[edge for edge,rows in edges.items() if len(rows)==2 and rows[0][1]==rows[1][1]]
    isolated=[i for i,v in enumerate(vertices) if v is not None and i not in incident]
    singular=[v for v,parts in fans.items() if len(parts)>1]
    finite=[i for i,v in enumerate(vertices) if v is not None];mapping={v:i for i,v in enumerate(finite)}
    counts={key:mesh[key] for key in ['invalidFaces','duplicateFaces','invalidUVs']}
    counts.update(nonManifoldEdges=len(nonmanifold),nonManifoldVertices=len(singular),inconsistentEdges=len(winding),isolatedVertices=len(isolated),invalidVertices=len(vertices)-len(finite))
    return {'counts':counts,'hasIssues':any(counts.values()),'vertexCount':len(vertices),'triangleCount':len(faces),
        'details':mesh['details'][:100],'detailsOmitted':max(0,len(mesh['details'])-100),
        'preview':{'vertices':[vertices[i] for i in finite],'faces':[[mapping[i] for i in f['v']] for f in faces]},
        'highlights':{'nonManifoldEdges':[vertices[v] for edge in nonmanifold for v in edge],
                      'inconsistentEdges':[vertices[v] for edge in winding for v in edge],
                      'invalidSegments':mesh['invalidSegments'],'invalidPoints':mesh['invalidPoints'],
                      'isolatedVertices':[vertices[i] for i in isolated], 'nonManifoldVertices':[vertices[i] for i in singular]}}


def diagnose_mesh(body):
    return report_mesh(read_mesh(body['text']))


def repair_mesh(body):
    mesh=read_mesh(body['text']);vertices=mesh['vertices'];faces=mesh['faces'];extras=mesh['extras']
    if not faces:raise ValueError('清理后没有有效三角面；无法生成可用模型。')
    def split_face(i):
        original=faces[i]['v'];ids=[]
        for v in original:ids.append(len(vertices));vertices.append(list(vertices[v]));extras.append(list(extras[v]))
        faces[i]['v']=ids
    edges,_,_,_=topology(faces,len(vertices))
    detach={i for rows in edges.values() if len(rows)>2 for i,_ in rows[2:]}
    for i in sorted(detach):split_face(i)
    # Orient patches. Cut conflicting cycles rather than guess or delete geometry.
    edges,_,_,_=topology(faces,len(vertices));adj=defaultdict(list)
    for rows in edges.values():
        if len(rows)==2:
            (a,da),(b,db)=rows;adj[a].append((b,da==db));adj[b].append((a,da==db))
    orientation={};cut=set()
    for seed in range(len(faces)):
        if seed in orientation:continue
        orientation[seed]=False;queue=deque([seed])
        while queue:
            a=queue.popleft()
            for b,opposite in adj[a]:
                required=orientation[a]^opposite
                if b not in orientation:orientation[b]=required;queue.append(b)
                elif orientation[b]!=required:cut.add(b)
    for i in sorted(cut):split_face(i)
    for i,flip in orientation.items():
        if flip:
            faces[i]['v'][1:]=faces[i]['v'][1:][::-1];faces[i]['uv'][1:]=faces[i]['uv'][1:][::-1]
    # Separate disconnected face fans around a shared (bow-tie) vertex.
    _,_,_,root=topology(faces,len(vertices));assigned={};first={}
    for i,face in enumerate(faces):
        for j,v in enumerate(list(face['v'])):
            key=(v,root(i*3+j))
            if key not in assigned:
                if v not in first:first[v]=key;assigned[key]=v
                else:assigned[key]=len(vertices);vertices.append(list(vertices[v]));extras.append(list(extras[v]))
            face['v'][j]=assigned[key]
    used=sorted({v for face in faces for v in face['v']});mapping={v:i for i,v in enumerate(used)}
    limit=MAX_SOURCE if body.get('side','source')=='source' else 200000
    if body.get('side','source') not in ('source','target'):raise ValueError('模型角色无效。')
    if len(used)>limit:raise ValueError(f'分离后超过该侧 {limit:,} 顶点上限，请先在建模软件中简化。')
    lines=['# Mesh Wave repaired mesh; triangulated; normals recomputed on import',*mesh['headers']]
    for v in used:lines.append('v '+' '.join(format(x,'.17g') for x in vertices[v])+(' '+' '.join(extras[v]) if extras[v] else ''))
    uv_mapping={}
    for i,uv in enumerate(mesh['uvs']):
        if uv is not None:uv_mapping[i]=len(uv_mapping);lines.append('vt '+' '.join(format(x,'.17g') for x in uv))
    previous=None
    for face in faces:
        if face['tags']!=previous:lines.extend(face['tags']);previous=face['tags']
        tokens=[]
        for v,u in zip(face['v'],face['uv']):tokens.append(str(mapping[v]+1)+(f'/{uv_mapping[u]+1}' if u is not None else ''))
        lines.append('f '+' '.join(tokens))
    text='\n'.join(lines)+'\n'
    if len(text.encode('utf-8'))>18*1024*1024:raise ValueError('修复后 OBJ 超过 18 MB 上限。')
    after=diagnose_mesh({'text':text})
    if after['hasIssues']:raise ValueError('修复后仍有未解决的网格问题，未生成可应用结果。')
    return {'text':text,'mesh':mesh_data(text),'report':after,'splitFaces':len(detach|cut)}
