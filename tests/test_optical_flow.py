import unittest
import numpy as np
from PIL import Image,ImageFilter,ImageOps
from optical_flow import refine_texture, render_mesh, cameras, photo_score
from flow_settings import flow_settings
from texture import png_texture,prepare_image,read_texture
from wrap_core import wrap
from project import validate_project
from test_features import project_fixture


def flow_fixture(side=25,shift=.035,flat=False):
    v=np.array([[x/(side-1),y/(side-1),0] for y in range(side) for x in range(side)])
    target=v.copy();g=np.sin(v[:,0]*np.pi)*np.sin(v[:,1]*np.pi)*np.exp(-((v[:,0]-.5)**2+(v[:,1]-.5)**2)/.08)
    g[(v[:,0]==0)|(v[:,0]==1)|(v[:,1]==0)|(v[:,1]==1)]=0;target[:,0]+=shift*g
    f=[]
    for y in range(side-1):
        for x in range(side-1):
            a=y*side+x;f.extend([[a,a+1,a+side+1],[a,a+side+1,a+side]])
    def textured(vertices):
        lines=['v '+' '.join(map(str,p)) for p in vertices]+['vt '+str(p[0])+' '+str(p[1]) for p in v]
        lines+=['f '+' '.join(f'{i+1}/{i+1}' for i in face) for face in f];return '\n'.join(lines)
    rng=np.random.default_rng(428);image=Image.fromarray(rng.integers(20,235,(256,256),dtype=np.uint8)).filter(ImageFilter.GaussianBlur(1)).convert('RGB') if not flat else Image.new('RGB',(256,256),(150,150,150))
    texture=png_texture(image,'skin.png');pairs=[[i,i] for i in [0,side-1,side*(side-1),side*side-1]]
    return {'source':textured(v),'target':textured(target),'vertices':v.tolist(),'pairs':pairs,'excludedFaces':{},'sourceTexture':texture,'targetTexture':texture,'cameraWorld':np.eye(4).flatten(order='F').tolist(),'settings':{'resolution':256,'iterations':2,'views':1,'strength':70,'distancePercent':6}},target,np.array(f)


class OpticalFlowTests(unittest.TestCase):
    def test_different_target_topology_and_mirrored_uv_layout(self):
        b,truth,_=flow_fixture();fine,_,_=flow_fixture(side=29)
        lines=[]
        for line in fine['target'].splitlines():
            if line.startswith('vt '):
                _,u,v=line.split();line=f'vt {1-float(u)} {v}'
            lines.append(line)
        b['target']='\n'.join(lines);b['targetTexture']=png_texture(ImageOps.mirror(read_texture(fine['targetTexture'])),'mirrored.png')
        b['pairs']=[[0,0],[24,28],[600,812],[624,840]];before=np.array(b['vertices']);result=refine_texture(b)
        self.assertEqual(len(result['vertices']),len(before));self.assertLess(np.linalg.norm(np.array(result['vertices'])-truth,axis=1).mean(),np.linalg.norm(before-truth,axis=1).mean())

    def test_real_optical_flow_improves_known_tangential_expression_motion(self):
        b,target,_=flow_fixture();before=np.array(b['vertices']);result=refine_texture(b);v=np.array(result['vertices']);stats=result['stats']
        self.assertLess(stats['afterPhotoError'],stats['beforePhotoError']);self.assertLess(np.linalg.norm(v-target,axis=1).mean(),np.linalg.norm(before-target,axis=1).mean())
        np.testing.assert_array_equal(v[[p[0] for p in b['pairs']]],before[[p[0] for p in b['pairs']]])
        self.assertGreaterEqual(stats['minProjectedAreaRatio'],.01);self.assertGreater(stats['matchedVertices'],10);self.assertEqual(v.shape,before.shape)

    def test_zero_soft_weights_stay_exact_and_all_locked_rejected(self):
        b,_,_=flow_fixture();v=np.array(b['vertices']);weights=np.ones(len(v));weights[(v[:,0]<.35)&(v[:,1]>.3)&(v[:,1]<.7)]=0;b['brushWeights']=weights.tolist()
        result=refine_texture(b);np.testing.assert_array_equal(np.array(result['vertices'])[weights==0],v[weights==0])
        b['brushWeights']=[0]*len(v)
        with self.assertRaises(ValueError):refine_texture(b)

    def test_flat_texture_or_missing_uv_does_not_produce_fake_refinement(self):
        b,_,_=flow_fixture(flat=True)
        with self.assertRaises(ValueError):refine_texture(b)
        b,_,_=flow_fixture();b['source']='\n'.join('f '+' '.join(t.split('/')[0] for t in l.split()[1:]) if l.startswith('f ') else l for l in b['source'].splitlines() if not l.startswith('vt '))
        with self.assertRaises(ValueError):refine_texture(b)

    def test_occluding_excluded_face_is_not_a_hole_into_the_rear_surface(self):
        b,_,f=flow_fixture(side=5,shift=0);v=np.array(b['vertices']);n=len(v);vertices=np.vstack([v,v+[0,0,-.01]]);faces=np.vstack([f,f+n]);uv=np.vstack([v[:,:2],v[:,:2]])
        image=prepare_image(Image.new('RGBA',(32,32),(180,180,180,255)));camera=cameras(vertices,vertices,np.eye(4).flatten(order='F'),1)[0]
        render=render_mesh(vertices,faces,uv,faces,image,camera,256,list(range(len(f))))
        self.assertFalse(render['valid'].any());self.assertTrue(np.any(render['face']>=0));self.assertTrue(np.all(render['face'][render['face']>=0]<len(f)))
        reversed_faces=faces.copy();reversed_faces[:len(f)]=reversed_faces[:len(f),::-1]
        render=render_mesh(vertices,reversed_faces,uv,reversed_faces,image,camera,256)
        self.assertFalse(render['valid'].any());self.assertTrue(np.all(render['face'][render['face']>=0]<len(f)))

    def test_settings_and_camera_validation(self):
        for value in [{'resolution':1024},{'iterations':0},{'strength':True},{'distancePercent':float('nan')},{'views':2}]:
            with self.assertRaises(ValueError):flow_settings(value)
        b,_,_=flow_fixture();b['cameraWorld']=[0]*16
        with self.assertRaises(ValueError):refine_texture(b)

    def test_single_iteration_uses_the_requested_render_resolution(self):
        b,_,_=flow_fixture(side=17);b['settings'].update(iterations=1,resolution=384)
        result=refine_texture(b);self.assertEqual(result['stats']['history'][0]['resolution'],384)
        self.assertLess(result['stats']['afterPhotoError'],result['stats']['beforePhotoError'])

    def test_multiview_refinement_preserves_additional_pins_and_exclusion_locks(self):
        b,_,faces=flow_fixture(side=17);b['pairs'].append([144,144]);b['excludedFaces']={'source':[10],'target':[15]}
        b['vertices']=wrap(b['source'],b['target'],b['pairs'],5,4,b['excludedFaces'])['vertices'];b['settings'].update(views=3,resolution=384)
        before=np.array(b['vertices']);result=refine_texture(b);after=np.array(result['vertices']);locked=np.unique(np.r_[[p[0] for p in b['pairs']],faces[10]])
        np.testing.assert_array_equal(after[locked],before[locked]);self.assertLess(result['stats']['afterPhotoError'],result['stats']['beforePhotoError'])
        self.assertEqual(result['stats']['views'],3)

    def test_transparent_texture_is_not_used_as_a_correspondence(self):
        b,_,_=flow_fixture();b['sourceTexture']=png_texture(Image.new('RGBA',(256,256),(200,200,200,0)),'empty.png')
        with self.assertRaises(ValueError):refine_texture(b)

    def test_project_flow_parameters_and_result_flag_roundtrip(self):
        p=project_fixture();self.assertEqual(validate_project(p)['settings']['flow'],flow_settings({}))
        from wrap_core import parse_obj
        v,_=parse_obj(p['models']['source']['text']);p['result']={'vertices':v.tolist(),'textureRefined':True};p['settings']['flow']=flow_settings({'views':1,'strength':70})
        restored=validate_project(p);self.assertTrue(restored['result']['textureRefined']);self.assertEqual(restored['settings']['flow'],p['settings']['flow'])
        p['result']['textureRefined']='yes'
        with self.assertRaises(ValueError):validate_project(p)
