// Read-only presentation helpers. Distances use OBJ units, not assumed millimeters.
export function summarizeQuality(report,threshold,ids=null){
  const values=[];let normalMismatch=0,normalUnknown=0,worst=null;
  for(const id of ids??report.distances.keys()){
    const d=report.distances[id];if(d===null||!Number.isFinite(d))continue;
    values.push(d);
    if(worst===null||d>report.distances[worst])worst=id;
    const angle=report.normalAngles[id];
    if(angle===null)normalUnknown++;else if(angle>report.normalAngle+1e-9)normalMismatch++;
  }
  values.sort((a,b)=>a-b);
  if(!values.length)return {count:0,worst:null};
  const percentile=p=>{const i=(values.length-1)*p,lo=Math.floor(i),hi=Math.ceil(i);return values[lo]+(values[hi]-values[lo])*(i-lo);};
  return {count:values.length,mean:values.reduce((a,b)=>a+b,0)/values.length,
    rms:Math.sqrt(values.reduce((a,b)=>a+b*b,0)/values.length),
    median:percentile(.5),p95:percentile(.95),max:values.at(-1),
    above:values.filter(d=>d>threshold).length,normalMismatch,normalUnknown,worst};
}
export function qualityColor(distance,threshold,angle,normalLimit,highlightNormals=false){
  if(distance===null||!Number.isFinite(distance))return [.24,.26,.29];
  if(highlightNormals&&angle!==null&&angle>normalLimit+1e-9)return [.65,.12,.85];
  const t=Math.max(0,Math.min(1,distance/threshold));
  const a=t<.5?[.04,.25,.85]:[1,.85,.05],b=t<.5?[1,.85,.05]:[.95,.04,.025],f=t<.5?t*2:(t-.5)*2;
  return a.map((x,i)=>x+(b[i]-x)*f);
}
export function buildQualityGraph(vertices,faces,distances){
  const graph=Array.from({length:vertices.length},()=>new Map());
  for(const face of faces)for(let i=0;i<3;i++){
    const a=face[i],b=face[(i+1)%3];
    if(distances[a]===null||distances[b]===null)continue;
    const d=Math.hypot(...vertices[a].map((x,j)=>x-vertices[b][j]));
    graph[a].set(b,d);graph[b].set(a,d);
  }
  return graph;
}
export function qualityRegion(graph,seed,radius){
  // Dijkstra on mesh edges avoids selecting nearby disconnected surfaces.
  const heap=[],best=new Map([[seed,0]]),region=[];
  const push=item=>{heap.push(item);let i=heap.length-1;while(i){const p=(i-1)>>1;if(heap[p][0]<=item[0])break;heap[i]=heap[p];i=p;}heap[i]=item;};
  const pop=()=>{const top=heap[0],last=heap.pop();if(heap.length){let i=0;while(i*2+1<heap.length){let c=i*2+1;if(c+1<heap.length&&heap[c+1][0]<heap[c][0])c++;if(heap[c][0]>=last[0])break;heap[i]=heap[c];i=c;}heap[i]=last;}return top;};
  push([0,seed]);
  while(heap.length){const [d,id]=pop();if(d!==best.get(id))continue;region.push(id);
    for(const [neighbor,length]of graph[id]){const next=d+length;if(next<=radius&&next<(best.get(neighbor)??Infinity)){best.set(neighbor,next);push([next,neighbor]);}}
  }
  return region;
}
