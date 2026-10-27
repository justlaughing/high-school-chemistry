(async () => {
  const progress = document.getElementById('progress'), frame = document.getElementById('benchmark'), resultNode = document.getElementById('result');
  const result = { passed: false, tested: 0, brokenImages: 0, textMismatches: [], mathMismatches: [], tableMismatches: [], benchmarks: [], environment: '本机127.0.0.1；浏览器会话首次读取及同会话复读；非公网测速' };
  const parse = html => new DOMParser().parseFromString(html, 'text/html');
  const cleanText = doc => { doc.querySelectorAll('.original summary').forEach(s => { if (s.textContent === '查看答案与解析') s.remove(); }); return doc.body.textContent; };
  const paths = await (await fetch('/__qa__/sources.json')).json();
  async function original(key) { const url = '/__baseline__/' + paths[key].split('/').map(encodeURIComponent).join('/'); return { url, html: await (await fetch(url)).text() }; }
  async function loadFrame(url, content) {
    const began = performance.now();
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(Error('阅读页加载超时')), 30000);
      frame.onload = async () => { try { await Promise.all([...frame.contentDocument.images].map(i => i.decode().catch(() => {})));clearTimeout(timer);resolve(); } catch(e){clearTimeout(timer);reject(e);} };
      if (content !== undefined) { frame.removeAttribute('src');frame.srcdoc = content; } else { frame.removeAttribute('srcdoc');frame.src = url; }
    });
    return +(performance.now() - began).toFixed(1);
  }
  try {
    const records = window.CHEM_BANK.records;
    const sample = records.filter((r,i) => records.findIndex(s => s.batch === r.batch) === i);
    const details = await (await fetch('/__qa__/evidence.json')).json();
    for (const criterion of ['images','mathml','tables']) { const rich = details.reduce((a,b) => b[criterion]>a[criterion]?b:a); const r=records.find(x=>x.key===rich.key);if(!sample.includes(r))sample.push(r); }
    const testedRecords=new URLSearchParams(location.search).has('compat')?sample:records;
    result.expected=testedRecords.length;result.mode=testedRecords===sample?'整包回退代表题核验':'全量分段读取核验';
    for (const record of sample) {
      progress.textContent = '测速：' + record.key;
      const source = await original(record.key);
      const oldMs = await loadFrame(source.url);
      let began = performance.now(), content = await ChemPacked.html(record.key);await loadFrame(null,content);const firstMs=+(performance.now()-began).toFixed(1);
      began=performance.now();content=await ChemPacked.html(record.key);await loadFrame(null,content);const repeatMs=+(performance.now()-began).toFixed(1);
      result.benchmarks.push({key:record.key,originalMs:oldMs,packedFirstMs:firstMs,packedRepeatMs:repeatMs});
    }
    for (const record of testedRecords) {
      progress.textContent = '完整性核验：' + (result.tested+1) + ' / '+testedRecords.length+' · '+record.key;
      const [source, packed] = await Promise.all([original(record.key),ChemPacked.html(record.key)]);
      const oldDoc=parse(source.html),newDoc=parse(packed);
      for (const [selector,target] of [['math','mathMismatches'],['table','tableMismatches']]) if(oldDoc.querySelectorAll(selector).length!==newDoc.querySelectorAll(selector).length)result[target].push(record.key);
      if(cleanText(oldDoc)!==cleanText(newDoc))result.textMismatches.push(record.key);
      await Promise.all([...newDoc.images].map(img => new Promise(resolve => { const test=new Image();test.onload=()=>resolve();test.onerror=()=>{result.brokenImages++;resolve();};test.src=img.src; })));
      result.tested++;
      if (result.tested % 100 === 0) result.cacheStats = ChemPacked.stats();
    }
    result.cacheStats = ChemPacked.stats();
    result.passed=result.tested===testedRecords.length&&!result.brokenImages&&!result.textMismatches.length&&!result.mathMismatches.length&&!result.tableMismatches.length&&result.cacheStats.questionPackCount<=8&&result.cacheStats.wholePackBytes<=result.cacheStats.packLimit;
    function percentile(field,p){const a=result.benchmarks.map(r=>r[field]).sort((a,b)=>a-b);return a[Math.min(a.length-1,Math.floor(a.length*p))];}
    result.timingSummary={samples:result.benchmarks.length,originalMedianMs:percentile('originalMs',.5),packedFirstMedianMs:percentile('packedFirstMs',.5),packedRepeatMedianMs:percentile('packedRepeatMs',.5),packedFirstP95Ms:percentile('packedFirstMs',.95)};
  } catch(error) {result.error=error.stack||error.message;}
  progress.textContent=result.passed?'全部'+result.tested+'题核验通过':'核验未通过';resultNode.textContent=JSON.stringify(result,null,2);
  await fetch('/__qa__/result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(result)});
})();
