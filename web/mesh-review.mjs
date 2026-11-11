import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

export class MeshReview {
  constructor(container){
    this.container=container;this.scene=new THREE.Scene();this.scene.background=new THREE.Color(0x151619);
    this.renderer=new THREE.WebGLRenderer({antialias:true});this.renderer.setPixelRatio(Math.min(devicePixelRatio,2));container.append(this.renderer.domElement);
    this.camera=new THREE.PerspectiveCamera(40,1,.001,10000);this.controls=new OrbitControls(this.camera,this.renderer.domElement);this.controls.enableDamping=true;
    this.scene.add(new THREE.HemisphereLight(0xffffff,0x353b45,2.2));const light=new THREE.DirectionalLight(0xffffff,2);light.position.set(3,5,7);this.scene.add(light);
    this.group=new THREE.Group();this.scene.add(this.group);this.layers={};this.visibility={};
    new ResizeObserver(()=>this.resize()).observe(container);
  }
  resize(){const w=Math.max(1,this.container.clientWidth),h=Math.max(1,this.container.clientHeight);this.renderer.setSize(w,h);this.camera.aspect=w/h;this.camera.updateProjectionMatrix();}
  show(report){
    for(const object of [...this.group.children]){object.geometry.dispose();object.material.dispose();this.group.remove(object);}this.layers={};
    const {vertices,faces}=report.preview,g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(vertices.flat(),3));g.setIndex(faces.flat());g.computeVertexNormals();
    this.group.add(new THREE.Mesh(g,new THREE.MeshStandardMaterial({color:0x77838e,roughness:.8,side:THREE.DoubleSide,transparent:true,opacity:.65})));
    const add=(name,positions,color,points=false)=>{
      if(!positions.length)return;const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions.flat(),3));
      const object=points?new THREE.Points(geometry,new THREE.PointsMaterial({color,size:8,sizeAttenuation:false,depthTest:false})):new THREE.LineSegments(geometry,new THREE.LineBasicMaterial({color,depthTest:false}));
      object.renderOrder={invalid:5,winding:8,nonmanifold:10,isolated:12}[name];object.visible=this.visibility[name]!==false;this.group.add(object);(this.layers[name]||=[]).push(object);
    };
    const h=report.highlights;
    add('nonmanifold',h.nonManifoldEdges,0xff5454);add('nonmanifold',h.nonManifoldVertices,0xff5454,true);
    add('invalid',h.invalidSegments,0xffbd61);add('invalid',h.invalidPoints,0xffbd61,true);
    add('isolated',h.isolatedVertices,0x61e1f0,true);add('winding',h.inconsistentEdges,0xd298ff);
    this.resize();const box=new THREE.Box3().setFromBufferAttribute(g.attributes.position),sphere=box.getBoundingSphere(new THREE.Sphere()),size=box.getSize(new THREE.Vector3()),r=Math.max(sphere.radius,1e-6);
    const distance=(Math.max(size.y,size.x/this.camera.aspect)/(2*Math.tan(THREE.MathUtils.degToRad(20))))*1.2+size.z/2;
    this.controls.target.copy(sphere.center);this.camera.position.copy(sphere.center).add(new THREE.Vector3(0,0,Math.max(distance,r*2)));
    this.camera.near=r/1000;this.camera.far=Math.max(distance,r*2)+r*100;this.camera.updateProjectionMatrix();this.controls.update();
  }
  visible(name,value){this.visibility[name]=value;for(const object of this.layers[name]||[])object.visible=value;}
  render(){this.controls.update();this.renderer.render(this.scene,this.camera);}
}
