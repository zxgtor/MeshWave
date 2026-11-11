import unittest
import numpy as np
from brush_support import prepare_brush,brush_settings
from project import validate_project
from test_features import project_fixture
from wrap_core import wrap,parse_obj


class BrushSupportTests(unittest.TestCase):
    def test_weight_project_roundtrip_and_legacy_defaults(self):
        p=project_fixture();self.assertIsNone(validate_project(p)['brushWeights'])
        v,_=parse_obj(p['models']['source']['text']);p['brushWeights']=[i/max(1,len(v)-1) for i in range(len(v))]
        self.assertEqual(validate_project(p)['brushWeights'],p['brushWeights'])

    def test_invalid_project_weights_rejected(self):
        p=project_fixture();v,_=parse_obj(p['models']['source']['text'])
        for weights in [[1],{},[True]*len(v),[-.1]*len(v),[1.1]*len(v),[float('nan')]*len(v),['.5']*len(v)]:
            p['brushWeights']=weights
            with self.assertRaises(ValueError):validate_project(p)

    def test_reference_preserves_landmark_and_region_locks(self):
        p=project_fixture();a,b=p['models']['source']['text'],p['models']['target']['text']
        result=wrap(a,b,p['pairs'],5,4,p['excludedFaces'])
        reference=prepare_brush({'source':a,'target':b,'pairs':p['pairs'],'vertices':result['vertices'],'excludedFaces':p['excludedFaces']})
        _,faces=parse_obj(a)
        self.assertEqual(set(reference['locked']),set(x[0] for x in p['pairs'])|set(faces[0]))
        self.assertEqual(len(reference['reference']),len(result['vertices']));self.assertGreater(reference['unit'],0)
        changed=np.array(result['vertices']);changed[p['pairs'][0][0],0]+=.1
        with self.assertRaises(ValueError):prepare_brush({'source':a,'target':b,'pairs':p['pairs'],'vertices':changed.tolist(),'excludedFaces':p['excludedFaces']})

    def test_project_keeps_manual_result_and_brush_settings(self):
        p=project_fixture();v,_=parse_obj(p['models']['source']['text']);p['result']={'vertices':v.tolist(),'manualEdits':True};p['settings']['brush']={'radiusPercent':7.5,'strength':60}
        restored=validate_project(p);self.assertTrue(restored['result']['manualEdits']);self.assertEqual(restored['settings']['brush'],p['settings']['brush'])
        p['result']['manualEdits']='yes'
        with self.assertRaises(ValueError):validate_project(p)

    def test_invalid_brush_settings_rejected(self):
        for settings in [{'radiusPercent':0},{'radiusPercent':21},{'strength':101},{'strength':False},{'strength':float('nan')}]:
            with self.assertRaises(ValueError):brush_settings(settings)


if __name__=='__main__':unittest.main()
