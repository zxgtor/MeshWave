export function pointPosition(vertices,faces,point){
  if(Number.isInteger(point))return vertices[point];
  return [0,1,2].map(axis=>point.bary.reduce((sum,w,i)=>sum+w*vertices[faces[point.face][i]][axis],0));
}
export function pointSupport(faces,point){
  return Number.isInteger(point)?[point]:faces[point.face].filter((_,i)=>point.bary[i]>1e-12);
}
export function pointKey(faces,point){
  const row=Number.isInteger(point)?[[point,1]]:faces[point.face].map((id,i)=>[id,Number(point.bary[i].toFixed(11))]).filter(([,w])=>w>1e-12);
  return JSON.stringify(row.sort((a,b)=>a[0]-b[0]));
}
export const samePoint=(faces,a,b)=>pointKey(faces,a)===pointKey(faces,b);
export const pointLabel=point=>Number.isInteger(point)?`#${point+1}`:`面 #${point.face+1}`;
export const pairKey=pair=>JSON.stringify(pair);
export function pointFromHit(vertices,faces,face,position){
  const [a,b,c]=faces[face].map(id=>vertices[id]);
  const sub=(x,y)=>x.map((v,i)=>v-y[i]),dot=(x,y)=>x.reduce((s,v,i)=>s+v*y[i],0);
  const u=sub(b,a),v=sub(c,a),p=sub(position,a),aa=dot(u,u),ab=dot(u,v),bb=dot(v,v),den=aa*bb-ab*ab;
  if(!Number.isFinite(den)||den<=0)throw Error('表面点不能位于退化三角面。');
  const y=(dot(p,u)*bb-dot(p,v)*ab)/den,z=(dot(p,v)*aa-dot(p,u)*ab)/den;
  const bary=[1-y-z,y,z].map(w=>Math.max(0,Math.min(1,w))),sum=bary.reduce((x,y)=>x+y,0);
  return {face,bary:bary.map(w=>w/sum)};
}
