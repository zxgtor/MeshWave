// Exact closest point on eligible target triangles, accelerated by an AABB tree.
const sub=(a,b)=>a.map((x,i)=>x-b[i]);
const dot=(a,b)=>a.reduce((s,x,i)=>s+x*b[i],0);
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
function closest(p,[a,b,c]){
  const ab=sub(b,a),ac=sub(c,a),ap=sub(p,a),n=cross(ab,ac),area=dot(n,n);
  const u=dot(cross(ap,ac),n)/area,v=dot(cross(ab,ap),n)/area;
  let best=null,distance=Infinity;
  const consider=q=>{const d=sub(p,q),d2=dot(d,d);if(d2<distance){best=q;distance=d2;}};
  if(u>=0&&v>=0&&u+v<=1)consider(a.map((x,i)=>x+u*ab[i]+v*ac[i]));
  for(const [start,end] of [[a,b],[b,c],[c,a]]){const e=sub(end,start),t=Math.max(0,Math.min(1,dot(sub(p,start),e)/dot(e,e)));consider(start.map((x,i)=>x+t*e[i]));}
  return {point:best,distance};
}
export class TargetSurface {
  constructor(vertices,faces,excluded=[],unit=1){
    this.unit=unit;this.origin=vertices[0];const skip=new Set(excluded),points=vertices.map(p=>sub(p,this.origin).map(x=>x/unit));
    const triangles=[];
    faces.forEach((f,id)=>{if(skip.has(id))return;const p=f.map(i=>points[i]),n=cross(sub(p[1],p[0]),sub(p[2],p[0])),size=Math.hypot(...n);if(size<=1e-14)return;
      triangles.push({p,n:n.map(x=>x/size),center:[0,1,2].map(j=>(p[0][j]+p[1][j]+p[2][j])/3)});
    });
    if(!triangles.length)throw Error('目标保留区域没有有效三角面，无法投射。');
    const build=items=>{
      const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
      for(const t of items)for(const p of t.p)for(let j=0;j<3;j++){lo[j]=Math.min(lo[j],p[j]);hi[j]=Math.max(hi[j],p[j]);}
      if(items.length<=16)return {lo,hi,items};
      const axis=[0,1,2].reduce((a,b)=>hi[a]-lo[a]>hi[b]-lo[b]?a:b);items.sort((a,b)=>a.center[axis]-b.center[axis]);const half=items.length>>1;
      return {lo,hi,children:[build(items.slice(0,half)),build(items.slice(half))]};
    };
    this.root=build(triangles);
  }
  query(point,normal,maxDistance,cosine){
    const p=sub(point,this.origin).map(x=>x/this.unit);let best=(maxDistance/this.unit)**2,answer=null;
    const bound=node=>[0,1,2].reduce((sum,j)=>sum+Math.max(node.lo[j]-p[j],p[j]-node.hi[j],0)**2,0);
    const stack=[this.root];
    while(stack.length){const node=stack.pop();if(bound(node)>best)continue;
      if(node.items){for(const t of node.items){if(dot(normal,t.n)<cosine)continue;const q=closest(p,t.p);if(q.distance<=best){best=q.distance;answer=q.point;}}}
      else{const [a,b]=node.children;if(bound(a)<bound(b))stack.push(b,a);else stack.push(a,b);}
    }
    return answer?.map((x,i)=>x*this.unit+this.origin[i])||null;
  }
}
