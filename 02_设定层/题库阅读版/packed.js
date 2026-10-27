(() => {
  'use strict';
  if (location.protocol === 'file:') { document.body.innerHTML = '<main style="max-width:760px;margin:60px auto;padding:24px;font:18px/1.8 sans-serif"><h1>高中化学题库</h1><p>新版已将全部题目和图片合并为数据包。请在“高中化学”文件夹中双击 <b>更新题库.cmd</b>，程序会启动本机阅读服务并打开首页。</p><p>本机运行不需要联网。原教材、试卷及旧版完整存档继续保留。</p></main>'; return; }
  const root = new URL('./', document.baseURI), jsons = new Map(), urls = new Map(), whole = new Map(), queues = new Map();
  const IMAGE_LIMIT=32*1024*1024, PACK_LIMIT=16*1024*1024, PACK_COUNT=8;
  let imageBytes=0,packBytes=0,history=[],peakImageBytes=0,peakPackBytes=0;
  const manifest=fetch(new URL('manifest.json',root),{cache:'no-cache'}).then(r=>{if(!r.ok)throw Error('读取题库清单失败');return r.json();});
  async function fileUrl(path){const m=await manifest;if(!m.files[path])throw Error('数据包未收入清单');return new URL(path+'?v='+m.files[path].sha256,root);}
  async function json(path){
    if(jsons.has(path)){const value=jsons.get(path);jsons.delete(path);jsons.set(path,value);return value;}
    const value=fileUrl(path).then(url=>fetch(url)).then(r=>{if(!r.ok)throw Error('题库已更新或数据包读取失败，请刷新页面');return r.json();}).catch(error=>{jsons.delete(path);throw error;});
    jsons.set(path,value);
    const questions=[...jsons.keys()].filter(k=>k.startsWith('questions/'));
    while(questions.length>PACK_COUNT)jsons.delete(questions.shift());
    return value;
  }
  function trim(){
    const pinned=new Set(history.flatMap(h=>h));
    for(const [hash,item] of urls){if(imageBytes<=IMAGE_LIMIT)break;if(pinned.has(hash)||!item.url)continue;URL.revokeObjectURL(item.url);urls.delete(hash);imageBytes-=item.bytes;}
    for(const [name,data] of whole){if(packBytes<=PACK_LIMIT)break;whole.delete(name);packBytes-=data.byteLength;}
    peakImageBytes=Math.max(peakImageBytes,imageBytes);peakPackBytes=Math.max(peakPackBytes,packBytes);
  }
  function bytesFromWhole(name,item){const data=whole.get(name);if(!data)return null;whole.delete(name);whole.set(name,data);return data.slice(item.offset,item.offset+item.length);}
  async function asset(hash,index){
    if(urls.has(hash)){const value=urls.get(hash);urls.delete(hash);urls.set(hash,value);return value.promise;}
    const info=index[hash];if(!info)throw Error('图片资源索引缺失');
    const item={bytes:0,url:null,promise:null};urls.set(hash,item);
    const task=(queues.get(info.pack)||Promise.resolve()).catch(()=>{}).then(async()=>{
      let data=bytesFromWhole(info.pack,info);
      if(!data){
        const response=await fetch(await fileUrl(info.pack),{headers:{Range:`bytes=${info.offset}-${info.offset+info.length-1}`}});
        if(!response.ok)throw Error('图片读取失败；题库可能已更新，请刷新');
        const buffer=await response.arrayBuffer();
        if(response.status===206){if(response.headers.get('Content-Range')!==`bytes ${info.offset}-${info.offset+info.length-1}/${(await manifest).files[info.pack].bytes}`)throw Error('图片分段响应不完整');data=buffer;}
        else{if(buffer.byteLength!==(await manifest).files[info.pack].bytes)throw Error('图片包长度不完整');whole.set(info.pack,buffer);packBytes+=buffer.byteLength;data=buffer.slice(info.offset,info.offset+info.length);trim();}
      }
      if(data.byteLength!==info.length)throw Error('图片长度不符');
      const actual=[...new Uint8Array(await crypto.subtle.digest('SHA-256',data))].map(x=>x.toString(16).padStart(2,'0')).join('');
      if(actual!==hash)throw Error('图片字节校验失败，请刷新后重试');
      item.url=URL.createObjectURL(new Blob([data],{type:info.mime}));item.bytes=data.byteLength;imageBytes+=item.bytes;trim();return item.url;
    }).catch(error=>{urls.delete(hash);throw error;});
    item.promise=task;const tail=task.then(()=>{},()=>{});queues.set(info.pack,tail);tail.then(()=>{if(queues.get(info.pack)===tail)queues.delete(info.pack);});return task;
  }
  async function html(key){
    const record=window.CHEM_BANK.records.find(r=>r.key===key);if(!record)throw Error('这道题未收入当前题库');
    const [questions,index,styles]=await Promise.all([json(record.pack),json('asset-index.json'),json('styles.json')]);
    const question=questions[key];if(!question)throw Error('整题正文缺失');
    history.push(question.assets);history=history.slice(-2);
    const loaded=new Map(await Promise.all(question.assets.map(async hash=>[hash,await asset(hash,index)])));
    let body=question.html.replace(/<!--chem-style:([a-f0-9]{64})-->/g,(_,hash)=>{if(!styles[hash])throw Error('原始样式缺失');return styles[hash];});
    body=body.replace(/chem-asset:([a-f0-9]{64}):\d+;/g,(_,hash)=>{if(!loaded.has(hash))throw Error('原图未加载');return loaded.get(hash);});
    const doc=new DOMParser().parseFromString(body,'text/html');doc.querySelectorAll('script').forEach(s=>s.remove());
    doc.querySelectorAll('.back').forEach(a=>{a.href=new URL('index.html',root).href;a.target='_top';});
    doc.querySelectorAll('.original details').forEach(d=>{if(/题干|配图|原题/.test(d.querySelector('summary')?.textContent||''))d.open=true;});
    doc.querySelectorAll('.original').forEach(original=>{
      const first=[...original.children].find(n=>/^H[23]$/.test(n.tagName)&&/^(原答案|原解析|答案|解析)$/.test(n.textContent.trim()));if(!first)return;
      const details=doc.createElement('details'),summary=doc.createElement('summary');summary.textContent='查看答案与解析';details.append(summary);original.insertBefore(details,first);
      for(let node=first;node;){const next=node.nextSibling;details.append(node);node=next;}
    });trim();return '<!doctype html>'+doc.documentElement.outerHTML;
  }
  async function preview(key,frame){
    const began=performance.now(),generation=String((Number(frame.dataset.generation)||0)+1);frame.dataset.generation=generation;frame.dataset.key=key;frame.dataset.state='loading';
    try{
      const content=await html(key);if(!frame.isConnected||frame.dataset.generation!==generation)return;
      const loaded=async()=>{frame.removeEventListener('load',loaded);if(frame.dataset.generation!==generation)return;const images=[...frame.contentDocument.images];await Promise.all(images.map(i=>i.decode().catch(()=>{})));if(frame.dataset.generation!==generation)return;frame.dataset.state=images.some(i=>!i.naturalWidth)?'error':'ready';frame.dataset.images=images.length;frame.dataset.milliseconds=(performance.now()-began).toFixed(1);frame.dispatchEvent(new CustomEvent('chem-ready'));};
      frame.addEventListener('load',loaded);frame.srcdoc=content;
    }catch(error){if(frame.dataset.generation!==generation)return;frame.dataset.state='error';const doc=document.implementation.createHTMLDocument('读取失败');doc.body.textContent=error.message;frame.srcdoc=doc.documentElement.outerHTML;frame.dispatchEvent(new CustomEvent('chem-ready'));}
  }
  function stats(){return {imageBytes,wholePackBytes:packBytes,imageCount:urls.size,questionPackCount:[...jsons.keys()].filter(k=>k.startsWith('questions/')).length,peakImageBytes,peakWholePackBytes:peakPackBytes,imageLimit:IMAGE_LIMIT,packLimit:PACK_LIMIT,pinnedAssets:new Set(history.flatMap(h=>h)).size};}
  window.ChemPacked={html,preview,stats};
  window.addEventListener('pagehide',()=>{for(const item of urls.values())if(item.url)URL.revokeObjectURL(item.url);urls.clear();whole.clear();});
})();
