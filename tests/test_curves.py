import copy
import unittest
import numpy as np
from curves import generate_curve_pairs, surface_graph, trace_path
from wrap_core import wrap,parse_obj
from project import validate_project
from test_core import obj


def fixture():
    v=np.array([[x/8,y/8,0] for y in range(9) for x in range(9)])
    f=[]
    for y in range(8):
        for x in range(8):
            a=y*9+x;f.extend([[a,a+1,a+10],[a,a+10,a+9]])
    target=v.copy();target[:,2]=.02*v[:,0]*v[:,1]
    return {'source':obj(v,f),'target':obj(target,f),'pairs':[[0,0],[8,8],[72,72]],'excludedFaces':{},'curves':[{'name':'lip','source':[37,43],'target':[37,43],'count':4,'closed':False}]}


class CurveTests(unittest.TestCase):
    def test_surface_arc_sampling_and_hard_solver_constraints(self):
        body=fixture();data=generate_curve_pairs(body)
        self.assertEqual(data['pairs'],[[37,37],[39,39],[41,41],[43,43]])
        self.assertEqual(data['paths'][0]['source'],list(range(37,44)))
        pairs=body['pairs']+data['pairs'];result=wrap(body['source'],body['target'],pairs,5)
        target,_=parse_obj(body['target'])
        np.testing.assert_allclose(np.array(result['vertices'])[[p[0] for p in pairs]],target[[p[1] for p in pairs]],atol=1e-12)
        self.assertEqual(len(result['vertices']),81)

    def test_closed_curve_has_unique_samples_and_consistent_start(self):
        b=fixture();b['curves'][0].update(source=[10,16,70,64],target=[10,16,70,64],count=8,closed=True)
        data=generate_curve_pairs(b);self.assertEqual(len(data['pairs']),8)
        self.assertEqual(data['pairs'][0],[10,10]);self.assertEqual(data['paths'][0]['source'][0],data['paths'][0]['source'][-1])

    def test_existing_exact_pairs_reused_but_crossed_mapping_rejected(self):
        b=fixture();b['pairs'].append([37,37]);data=generate_curve_pairs(b)
        self.assertEqual(len(data['pairs']),3)
        b['curves'][0]['target'].reverse()
        with self.assertRaises(ValueError):generate_curve_pairs(b)

    def test_dense_sampling_duplicate_controls_and_backtracking_rejected(self):
        for changes in [{'count':30},{'source':[37,37]},{'source':[37,43,39]},{'source':[True,43]},{'count':2.5},{'closed':'yes'}]:
            b=fixture();b['curves'][0].update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):generate_curve_pairs(b)

    def test_paths_never_bridge_disconnected_close_sheets(self):
        b=fixture();v,f=parse_obj(b['source']);v=np.vstack([v,v+[0,0,.0001]]);f=np.vstack([f,f+81]);g=surface_graph(v,f,[])
        with self.assertRaises(ValueError):trace_path(g,[37,43+81])

    def test_excluded_vertices_and_separating_strip_block_curves(self):
        b=fixture();_,f=parse_obj(b['source']);b['excludedFaces']={'target':[int(np.flatnonzero(np.any(f==37,axis=1))[0])]}
        with self.assertRaises(ValueError):generate_curve_pairs(b)
        b=fixture();v,f=parse_obj(b['source']);strip=np.flatnonzero(np.any(np.isin(f,[4+9*y for y in range(9)]),axis=1)).tolist()
        with self.assertRaises(ValueError):trace_path(surface_graph(v,f,strip),[37,43])

    def test_incomplete_curves_preview_and_project_roundtrip(self):
        b=fixture();b['curves'][0]['target']=[];b['pathOnly']=True
        data=generate_curve_pairs(b);self.assertEqual(data['pairs'],[]);self.assertEqual(data['paths'][0]['target'],[])
        p={'format':'facewrap-lite','version':1,'models':{s:{'name':s+'.obj','text':b[s]} for s in ['source','target']},'pairs':b['pairs'],'curves':b['curves'],'curvePairs':[]}
        self.assertEqual(validate_project(p)['curves'],b['curves'])
        del p['curves'];self.assertEqual(validate_project(p)['curves'],[])
        p['curvePairs']=[[37,37]]
        with self.assertRaises(ValueError):validate_project(p)

    def test_multiple_curves_merge_shared_endpoints_and_conflicts_atomically(self):
        b=fixture();b['curves'].append({'name':'nose','source':[43,70],'target':[43,70],'count':3,'closed':False})
        data=generate_curve_pairs(b);self.assertEqual(len(data['pairs']),6)
        previous=copy.deepcopy(b);b['curves'][1]['target']=[42,70]
        with self.assertRaises(ValueError):generate_curve_pairs(b)
        self.assertEqual(previous['pairs'],b['pairs'])

    def test_combined_pair_limit_and_empty_curve_removal_preview(self):
        b=fixture();b['curves']=[];self.assertEqual(generate_curve_pairs(b),{'paths':[],'pairs':[]})
        v=[[x,y,0] for y in range(4) for x in range(31)];f=[]
        for y in range(3):
            for x in range(30):
                a=y*31+x;f.extend([[a,a+1,a+32],[a,a+32,a+31]])
        text=obj(v,f);b={'source':text,'target':text,'pairs':[],'curves':[{'name':str(y),'source':[y*31,y*31+30],'target':[y*31,y*31+30],'count':30,'closed':False} for y in range(4)]}
        with self.assertRaisesRegex(ValueError,'100'):generate_curve_pairs(b)
