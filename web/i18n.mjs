import interfaceMessages from './i18n-catalog.mjs';
import runtimeMessages from './i18n-messages.mjs';
import errorMessages from './i18n-errors.mjs';

export const messages=new Map([...interfaceMessages,...runtimeMessages,...errorMessages]);
const escape=value=>value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
const phrases=new RegExp([...messages.keys()].sort((a,b)=>b.length-a.length).map(escape).join('|'),'g');
const bindings=new WeakMap(),attributes=new WeakMap(),userNames=new Set();
const storageKey='mesh-wave-language';
let language='zh-CN';
try{if(globalThis.localStorage?.getItem(storageKey)==='en')language='en';}catch{}
export const getLanguage=()=>language;

// File names are data, even when they contain words used in the interface.
export function preserveName(value){
  const text=String(value??'');
  if(text&&(/[.\\/]/.test(text)||/^“.*”$/.test(text)))userNames.add(text);
  return text;
}
export function translate(text,locale=language){
  const source=String(text??'');
  if(locale!=='en'||!/[\u3400-\u9fff]/.test(source))return source;
  const names=[];
  let protectedText=source;
  for(const name of [...userNames].sort((a,b)=>b.length-a.length)){
    if(protectedText.includes(name)){
      const token=`\uE000${names.length}\uE001`;names.push(name);
      protectedText=protectedText.split(name).join(token);
    }
  }
  const exact=messages.get(protectedText.trim());
  let result=exact??protectedText.replace(phrases,key=>` ${messages.get(key)} `)
    .replace(/[\t \u3000]+/g,' ').replace(/，/g,', ').replace(/。/g,'. ')
    .replace(/；/g,'; ').replace(/：/g,': ').replace(/（/g,' (').replace(/）/g,') ')
    .replace(/、/g,', ').replace(/ +([,.;:])/g,'$1').trim();
  result=result.replace(/\uE000(\d+)\uE001/g,(_,index)=>names[Number(index)]);
  return result;
}

// Keep source text separate from rendered text, including incremental status updates.
export function setText(node,value,literal=false){
  const source=String(value??'');
  bindings.set(node,{source,literal});
  if(literal)preserveName(source);
  node.textContent=literal?source:translate(source);
  return value;
}
export const getSourceText=node=>bindings.get(node)?.source??node.textContent;
export function appendText(node,value){
  return setText(node,getSourceText(node)+String(value??''));
}
export function setLabel(node,name,value,literal=false){
  const labels=attributes.get(node)??new Map();attributes.set(node,labels);
  const source=String(value??'');labels.set(name,{source,literal});
  node.setAttribute(name,literal?source:translate(source));
  return value;
}
function refresh(root){
  const binding=bindings.get(root);
  if(binding){
    const text=binding.literal?binding.source:translate(binding.source);
    if(root.textContent!==text)root.textContent=text;
  }
  for(const [name,label]of attributes.get(root)??[]){
    root.setAttribute(name,label.literal?label.source:translate(label.source));
  }
  if(!binding)for(const child of [...root.childNodes])refresh(child);
}
function bindStatic(root){
  if(root.nodeType===1){
    if(root.matches('script,style,input,[data-i18n-ignore]'))return;
    for(const name of ['title','aria-label','alt']){
      if(root.hasAttribute(name))setLabel(root,name,root.getAttribute(name));
    }
  }
  if(root.nodeType===3&&/[\u3400-\u9fff]/.test(root.data)){
    const raw=root.data,trimmed=raw.trim();
    // Preserve HTML whitespace around inline labels and controls.
    const text=translate(trimmed);bindings.set(root,{source:raw,literal:false});
    root.data=raw.replace(trimmed,text);return;
  }
  for(const child of [...root.childNodes])bindStatic(child);
}
export function setLanguage(value){
  language=value==='en'?'en':'zh-CN';
  try{localStorage.setItem(storageKey,language);}catch{}
  document.documentElement.lang=language;
  document.getElementById('language-select').value=language;
  refresh(document.head);refresh(document.body);
}
export function initializeLanguage(){
  // Capture selected filenames before application handlers use them in status messages.
  document.addEventListener('change',event=>{
    if(event.target.type==='file')for(const file of event.target.files??[])preserveName(file.name);
  },true);
  bindStatic(document.head);bindStatic(document.body);
  const select=document.getElementById('language-select');
  select.addEventListener('change',()=>setLanguage(select.value));
  select.value=language;document.documentElement.lang=language;
}
