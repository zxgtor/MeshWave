import test from 'node:test';
import assert from 'node:assert/strict';
import {messages,translate,preserveName,setText,appendText} from '../web/i18n.mjs';

test('formats dynamic statistics and server errors in English',()=>{
  assert.equal(translate('有效 UV 像素覆盖率 100.0% · 0 像素未匹配 · 0 个零面积 UV 面','en'),
    'Valid UV pixel coverage 100.0% · 0 unmatched pixels · 0 zero-area UV faces');
  assert.equal(translate('对应点不能重合或位于同一直线上，请分散选择。','en'),
    'Correspondences must not coincide or be collinear. Spread them across the mesh.');
});
test('preserves filenames and paths containing interface words',()=>{
  const name='目标 模板.测试.obj',path='E:\\项目\\目标 模板.obj';
  preserveName(name);preserveName(path);
  assert.equal(translate(`正在读取 ${name}…`,'en'),`Reading ${name}…`);
  assert.equal(translate(`结果目录：${path}`,'en'),`Output folder: ${path}`);
});
test('Chinese messages and English data pass through unchanged',()=>{
  const source='已打开工程：用户工程.facewrap.json';
  assert.equal(translate(source,'zh-CN'),source);
  assert.equal(translate('mesh_template.obj','en'),'mesh_template.obj');
});
test('keeps custom curve names inside localized diagnostics',()=>{
  preserveName('“目标曲线”');
  assert.equal(translate('曲线“目标曲线”两侧控制节点不足。','en'),
    'Curve “目标曲线”: insufficient control points on one or both sides.');
});
test('incremental status updates retain source text rather than translated text',()=>{
  const node={id:'health-status',textContent:''};
  setText(node,'正在检查网格…');appendText(node,' 无效面');
  assert.equal(node.textContent,'正在检查网格… 无效面');
});
test('file labels retain user spelling and literal messages never change',()=>{
  const node={id:'source-name',textContent:''};
  setText(node,'目标.模板.obj',true);assert.equal(node.textContent,'目标.模板.obj');
  const item={textContent:''};setText(item,'正在处理',true);
  assert.equal(item.textContent,'正在处理');
});
test('all catalog entries have English text without untranslated Chinese',()=>{
  for(const [source,english]of messages){
    assert.ok(source.length&&english?.length,source);
    assert.doesNotMatch(english,/[\u3400-\u9fff]/,source);
  }
});
