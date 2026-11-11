import {copyFile, cp, mkdir} from 'node:fs/promises';
await mkdir('web/vendor',{recursive:true});
for(const name of ['three.module.js','three.core.js'])await copyFile(`node_modules/three/build/${name}`,`web/vendor/${name}`);
for(const folder of ['controls','renderers'])await cp(`node_modules/three/examples/jsm/${folder}`,`web/vendor/addons/${folder}`,{recursive:true});
await copyFile('node_modules/three/LICENSE','web/vendor/THREE-LICENSE.txt');
