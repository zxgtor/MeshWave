import math


def flow_settings(value):
    if not isinstance(value,dict):raise ValueError('纹理细化参数格式无效。')
    defaults={'resolution':384,'iterations':2,'strength':50,'distancePercent':3,'views':3}
    result={key:value.get(key,default) for key,default in defaults.items()}
    if type(result['resolution']) is not int or result['resolution'] not in (256,384,512) or type(result['iterations']) is not int or not 1<=result['iterations']<=5 or type(result['views']) is not int or result['views'] not in (1,3):
        raise ValueError('纹理细化分辨率为 256/384/512，迭代 1–5 次，视图数为 1 或 3。')
    for key,low,high in [('strength',1,100),('distancePercent',.1,10)]:
        v=result[key]
        if type(v) not in (int,float) or not math.isfinite(v) or not low<=v<=high:raise ValueError('纹理细化强度为 1–100，最大位移为目标尺寸的 0.1%–10%。')
    return result
