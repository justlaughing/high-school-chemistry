(() => {
  if(!/^https?:$/.test(location.protocol))return;
  let initial=null,busy=false,shown=false;
  async function check(){
    if(busy||document.hidden)return;busy=true;
    try{const response=await fetch('manifest.json',{cache:'no-store'});if(!response.ok)return;const data=await response.json();const version=JSON.stringify(data.files);if(!initial)initial=version;else if(initial!==version&&!shown){shown=true;const bar=document.createElement('div');bar.setAttribute('role','status');bar.style.cssText='position:fixed;bottom:12px;left:12px;right:12px;padding:14px;background:#173f54;color:white;z-index:9999;border-radius:8px';bar.append('题库内容已更新。');const button=document.createElement('button');button.textContent='刷新读取新版';button.onclick=()=>location.reload();bar.append(button);document.body.append(bar);}if(['localhost','127.0.0.1'].includes(location.hostname)){const health=await(await fetch('api/health',{cache:'no-store'})).json();const label=document.getElementById('monitor-status');if(label){label.dataset.normalText||=label.textContent;label.textContent=health.error?'新分类数据读取遇到问题，保留上次完整题库：'+health.error:label.dataset.normalText;label.classList.toggle('problem',Boolean(health.error));}}}catch(_){}finally{busy=false;}
  }
  check();setInterval(check,5000);document.addEventListener('visibilitychange',check);
})();
