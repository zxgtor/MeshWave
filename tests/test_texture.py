import base64
import copy
import io
import unittest
import zipfile
import numpy as np
from PIL import Image
from project import validate_project
from wrap_core import parse_obj, mesh_data
from texture import (png_texture, read_texture, normalize_texture, bake_texture,
                     texture_bundle, sample_image)


def plane(rotated=False):
    uv = [[1,0],[1,1],[0,1],[0,0]] if rotated else [[0,0],[1,0],[1,1],[0,1]]
    return '\n'.join(['v 0 0 0','v 1 0 0','v 1 1 0','v 0 1 0'] +
        ['vt '+' '.join(map(str,p)) for p in uv] + ['f 1/1 2/2 3/3','f 1/1 3/3 4/4'])


def quadrants():
    pixels=np.zeros((32,32,4),dtype=np.uint8);pixels[:,:,3]=255
    pixels[:16,:16,:3]=[255,0,0];pixels[:16,16:,:3]=[0,255,0]
    pixels[16:,:16,:3]=[0,0,255];pixels[16:,16:,:3]=[255,255,0]
    return png_texture(Image.fromarray(pixels),'quadrants.png')


def texture_project():
    text=plane(True);target=plane();v,_=parse_obj(text)
    return {'format':'facewrap-lite','version':1,
        'models':{'source':{'name':'template.obj','text':text,'texture':quadrants()},
                  'target':{'name':'scan.obj','text':target,'texture':quadrants()}},
        'pairs':[[i,i] for i in range(4)],'pending':None,'excludedFaces':{'source':[],'target':[]},
        'settings':{'iterations':5,'smoothness':4,'normalAngle':60,
                    'bake':{'resolution':256,'padding':0,'distanceRatio':.02}},
        'result':{'vertices':v.tolist()}}


class TextureTests(unittest.TestCase):
    def test_obj_corner_uv_negative_indices_and_seam(self):
        text=plane()+'\nvt .2 .3\nf -4/-1 -2/-3 -1/-2'
        v,f,uv,uf=parse_obj(text,True)
        self.assertEqual(len(v),4);self.assertEqual(len(uv),5)
        np.testing.assert_array_equal(uf[-1],[4,2,3])
        self.assertTrue(mesh_data(text)['hasUV'])
        self.assertFalse(mesh_data('v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3')['hasUV'])
        with self.assertRaises(ValueError):parse_obj(plane().replace('1/1','1/99'),True)

    def test_png_jpeg_normalization_and_bad_input(self):
        texture=quadrants();self.assertEqual(normalize_texture(texture)['height'],32)
        buffer=io.BytesIO();read_texture(texture).convert('RGB').save(buffer,format='JPEG')
        jpeg={'name':'scan.jpg','dataUrl':'data:image/jpeg;base64,'+base64.b64encode(buffer.getvalue()).decode()}
        self.assertTrue(normalize_texture(jpeg)['dataUrl'].startswith('data:image/png;base64,'))
        for invalid in [{'name':'x','dataUrl':'data:image/png;base64,not-an-image'},
                        {'name':'x','dataUrl':'data:text/html;base64,AAAA'}]:
            with self.assertRaises(ValueError):normalize_texture(invalid)

    def test_linear_light_bilinear_and_premultiplied_alpha(self):
        image=Image.fromarray(np.array([[[0,0,0,255],[255,255,255,255]]],dtype=np.uint8))
        np.testing.assert_allclose(sample_image(image,np.array([[.5,.5]])),[[188,188,188,255]],atol=1)
        alpha=Image.fromarray(np.array([[[255,0,0,0],[0,0,255,255]]],dtype=np.uint8))
        np.testing.assert_allclose(sample_image(alpha,np.array([[.5,.5]])),[[0,0,255,128]],atol=1)

    def test_bake_transfers_into_rotated_template_uv_without_vertical_flip(self):
        source,target=plane(True),plane();v,_=parse_obj(source)
        result=bake_texture(source,target,v,quadrants(),256,0)
        output=np.asarray(read_texture(result['texture']))
        np.testing.assert_array_equal(output[64,64],[0,255,0,255])
        np.testing.assert_array_equal(output[64,192],[255,255,0,255])
        np.testing.assert_array_equal(output[192,64],[255,0,0,255])
        np.testing.assert_array_equal(output[192,192],[0,0,255,255])
        self.assertEqual(result['stats']['coverage'],1)
        self.assertEqual(result['stats']['atlasPixels'],256*256)

    def test_excluded_regions_are_transparent_and_target_not_sampled(self):
        source,target=plane(),plane();v,_=parse_obj(source)
        excluded=bake_texture(source,target,v,quadrants(),256,0,excluded_faces={'source':[0]})
        pixels=np.asarray(read_texture(excluded['texture']))
        self.assertEqual(pixels[192,192,3],0);self.assertEqual(pixels[64,64,3],255)
        excluded=bake_texture(source,target,v,quadrants(),256,0,excluded_faces={'target':[0]})
        pixels=np.asarray(read_texture(excluded['texture']))
        self.assertEqual(pixels[192,192,3],0);self.assertEqual(pixels[64,64,3],255)
        self.assertGreater(excluded['stats']['unmatchedPixels'],100)

    def test_target_uv_seam_uses_per_corner_indices(self):
        target='\n'.join(['v 0 0 0','v 1 0 0','v 1 1 0','v 0 1 0',
            'vt .05 .55','vt .45 .55','vt .45 .95','vt .55 .55','vt .95 .95','vt .55 .95',
            'f 1/1 2/2 3/3','f 1/4 3/5 4/6'])
        vertices,_=parse_obj(plane())
        result=bake_texture(plane(),target,vertices,quadrants(),256,0)
        pixels=np.asarray(read_texture(result['texture']))
        np.testing.assert_array_equal(pixels[192,192],[255,0,0,255])
        np.testing.assert_array_equal(pixels[64,64],[0,255,0,255])

    def test_padding_only_grows_outside_islands_and_keeps_missing_pixels(self):
        source=plane().replace('vt 0 0','vt .25 .25').replace('vt 1 0','vt .75 .25').replace('vt 1 1','vt .75 .75').replace('vt 0 1','vt .25 .75')
        v,_=parse_obj(source)
        result=bake_texture(source,plane(),v,quadrants(),256,4,excluded_faces={'source':[0]})
        pixels=np.asarray(read_texture(result['texture']))
        self.assertEqual(pixels[80,62,3],255)
        self.assertEqual(pixels[80,55,3],0)
        self.assertEqual(pixels[170,170,3],0)

    def test_invalid_uv_distance_and_normals_rejected(self):
        source=plane();v,_=parse_obj(source)
        missing='\n'.join(line for line in source.splitlines() if not line.startswith('vt ')).replace('/1','').replace('/2','').replace('/3','').replace('/4','')
        with self.assertRaises(ValueError):bake_texture(missing,plane(),v,quadrants(),256)
        with self.assertRaises(ValueError):bake_texture(source,missing,v,quadrants(),256)
        with self.assertRaisesRegex(ValueError,'0–1'):bake_texture(source.replace('vt 1 1','vt 2 1'),plane(),v,quadrants(),256)
        with self.assertRaisesRegex(ValueError,'重叠'):bake_texture(source+'\nf 1/1 2/2 3/3',plane(),v,quadrants(),256)
        with self.assertRaisesRegex(ValueError,'没有像素'):bake_texture(source,plane(),v+[0,0,.1],quadrants(),256)
        reversed_target=plane().replace('f 1/1 2/2 3/3','f 3/3 2/2 1/1').replace('f 1/1 3/3 4/4','f 4/4 3/3 1/1')
        with self.assertRaisesRegex(ValueError,'没有像素'):bake_texture(source,reversed_target,v,quadrants(),256)

    def test_texture_bundle_material_uv_and_pixels_are_portable(self):
        source='mtllib old.mtl\nusemtl\told\n'+plane(True)
        v,_=parse_obj(source);result=bake_texture(source,plane(),v,quadrants(),256,0)
        with zipfile.ZipFile(io.BytesIO(texture_bundle(source,v,result['texture']))) as archive:
            self.assertEqual(set(archive.namelist()),{'model.obj','model.mtl','texture.png','opacity.png'})
            exported=archive.read('model.obj').decode()
            self.assertIn('mtllib model.mtl',exported);self.assertNotIn('old',exported)
            self.assertIn('map_Kd texture.png',archive.read('model.mtl').decode())
            np.testing.assert_array_equal(np.asarray(Image.open(io.BytesIO(archive.read('texture.png')))),np.asarray(read_texture(result['texture'])))
            _,f,uv,uf=parse_obj(exported,True);_,ff,uu,ufuf=parse_obj(source,True)
            np.testing.assert_array_equal(f,ff);np.testing.assert_array_equal(uv,uu);np.testing.assert_array_equal(uf,ufuf)

    def test_project_roundtrip_preserves_input_and_baked_textures(self):
        project=texture_project();project['result']['texture']=bake_texture(plane(True),plane(),project['result']['vertices'],quadrants(),256,0)['texture']
        validated=validate_project(project)
        self.assertEqual(validated['settings']['bake'],project['settings']['bake'])
        for actual,expected in [(validated['models']['target']['texture'],project['models']['target']['texture']),
                                (validated['result']['texture'],project['result']['texture'])]:
            np.testing.assert_array_equal(np.asarray(read_texture(actual)),np.asarray(read_texture(expected)))
        self.assertTrue(validated['models']['source']['hasUV'])
        invalid=copy.deepcopy(project);invalid['settings']['bake']['resolution']=999
        with self.assertRaises(ValueError):validate_project(invalid)


if __name__=='__main__':unittest.main()
