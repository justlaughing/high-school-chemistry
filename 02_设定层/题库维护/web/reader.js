(() => {
  const frame = document.getElementById('packed-reader'), status = document.getElementById('reader-status');
  frame.addEventListener('chem-ready', () => { status.textContent = frame.dataset.state === 'ready' ? `完整题目已加载 · ${frame.dataset.images}张图片` : '读取失败，请返回题库重试'; });
  function show() { const key = decodeURIComponent(location.hash.slice(1)); document.title = (window.CHEM_BANK.records.find(r => r.key === key)?.title || '完整题目') + ' · 分包阅读版'; window.ChemPacked.preview(key, frame); }
  window.addEventListener('hashchange', show); show();
})();
