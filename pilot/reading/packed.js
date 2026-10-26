(() => {
  'use strict';
  const root = new URL('./', document.baseURI), pending = new Map(), objectUrls = new Map(), wholePacks = new Map(), packQueues = new Map();
  const manifest = fetch(new URL('manifest.json', root), { cache: 'no-cache' }).then(r => { if (!r.ok) throw Error('无法读取阅读版清单'); return r.json(); });
  async function fileUrl(path) { const m = await manifest; return new URL(path + '?v=' + m.files[path].sha256, root); }
  function json(path) {
    if (!pending.has(path)) pending.set(path, fileUrl(path).then(url => fetch(url)).then(r => { if (!r.ok) throw Error('数据包读取失败：' + path); return r.json(); }));
    return pending.get(path);
  }
  async function asset(digest, index) {
    if (objectUrls.has(digest)) return objectUrls.get(digest);
    const item = index[digest]; if (!item) throw Error('图片未收入资源索引');
    const task = (packQueues.get(item.pack) || Promise.resolve()).catch(() => {}).then(async () => {
      let data;
      if (wholePacks.has(item.pack)) data = wholePacks.get(item.pack).slice(item.offset, item.offset + item.length);
      else {
        const response = await fetch(await fileUrl(item.pack), { headers: { Range: `bytes=${item.offset}-${item.offset + item.length - 1}` } });
        if (!response.ok) throw Error('图片资源包读取失败');
        const buffer = await response.arrayBuffer();
        if (response.status === 206) data = buffer;
        else { wholePacks.set(item.pack, buffer); data = buffer.slice(item.offset, item.offset + item.length); }
      }
      if (data.byteLength !== item.length) throw Error('图片资源长度不符');
      const actual = [...new Uint8Array(await crypto.subtle.digest('SHA-256', data))].map(x => x.toString(16).padStart(2, '0')).join('');
      if (actual !== digest) throw Error('图片资源校验失败');
      return URL.createObjectURL(new Blob([data], { type: item.mime }));
    });
    packQueues.set(item.pack, task.then(() => {})); objectUrls.set(digest, task); return task;
  }
  async function html(key) {
    const record = window.CHEM_BANK.records.find(r => r.key === key); if (!record) throw Error('这道题未收入180题试验样本');
    const [questions, index, styles] = await Promise.all([json(record.pack), json('asset-index.json'), json('styles.json')]);
    const question = questions[key]; if (!question) throw Error('题目数据包缺少此题');
    const urls = new Map(await Promise.all(question.assets.map(async hash => [hash, await asset(hash, index)])));
    let body = question.html.replace(/<!--chem-style:([a-f0-9]{64})-->/g, (_, hash) => { if (!styles[hash]) throw Error('阅读样式缺失'); return styles[hash]; });
    body = body.replace(/chem-asset:([a-f0-9]{64}):\d+;/g, (_, hash) => { if (!urls.has(hash)) throw Error('图片数据未加载'); return urls.get(hash); });
    const doc = new DOMParser().parseFromString(body, 'text/html');
    doc.querySelectorAll('script').forEach(s => s.remove());
    doc.querySelectorAll('.back').forEach(a => { a.href = new URL('index.html', root).href; a.target = '_top'; });
    doc.querySelectorAll('.original details').forEach(d => { if (/题干|配图|原题/.test(d.querySelector('summary')?.textContent || '')) d.open = true; });
    doc.querySelectorAll('.original').forEach(original => {
      const first = [...original.children].find(n => /^H[23]$/.test(n.tagName) && /^(原答案|原解析|答案|解析)$/.test(n.textContent.trim()));
      if (!first) return;
      const details = doc.createElement('details'), summary = doc.createElement('summary'); summary.textContent = '查看答案与解析'; details.append(summary); original.insertBefore(details, first);
      for (let node = first; node;) { const next = node.nextSibling; details.append(node); node = next; }
    });
    return '<!doctype html>' + doc.documentElement.outerHTML;
  }
  async function preview(key, frame) {
    const began = performance.now(); frame.dataset.key = key; frame.dataset.state = 'loading';
    try {
      const content = await html(key); if (!frame.isConnected || frame.dataset.key !== key) return;
      frame.addEventListener('load', async function loaded() {
        frame.removeEventListener('load', loaded);
        const images = [...frame.contentDocument.images];
        await Promise.all(images.map(img => img.decode().catch(() => {})));
        frame.dataset.state = images.some(img => !img.naturalWidth) ? 'error' : 'ready';
        frame.dataset.milliseconds = (performance.now() - began).toFixed(1);
        frame.dataset.images = images.length;
        frame.dispatchEvent(new CustomEvent('chem-ready'));
      });
      frame.srcdoc = content;
    } catch (error) {
      frame.dataset.state = 'error'; const errorDoc = document.implementation.createHTMLDocument('读取失败'); errorDoc.body.textContent = error.message; frame.srcdoc = errorDoc.documentElement.outerHTML;
      frame.dispatchEvent(new CustomEvent('chem-ready'));
    }
  }
  window.ChemPacked = { html, preview };
  window.addEventListener('pagehide', () => { for (const promise of objectUrls.values()) Promise.resolve(promise).then(url => URL.revokeObjectURL(url)); });
})();
