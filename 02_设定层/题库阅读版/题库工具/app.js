(() => {
  'use strict';
  const under = (tag, path) => tag === path || tag.startsWith(path + '/');
  function match(record, criteria) {
    const tags = criteria.scope === 'main' ? [record.main] : record.tags;
    const words = criteria.query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const hay = record.searchText || [record.key, record.id, record.title, record.paper_label, record.text, ...record.tags, ...record.subquestions.map(s => s.focus || '')].join(' ').toLowerCase();
    return criteria.selected.every(path => tags.some(tag => under(tag, path))) &&
      (!criteria.type || record.question_type === criteria.type) &&
      (!criteria.batch || record.batch === criteria.batch) &&
      (!criteria.paper || record.batch + ':' + record.paper_id === criteria.paper) &&
      words.every(word => hay.includes(word)) &&
      (!criteria.quick || tags.some(t => (quickPaths[criteria.quick] || []).some(p => under(t, p))));
  }
  const quickPaths = {
    ions: ['化学反应原理/水的电离及溶液的酸碱性', '化学反应原理/弱电解质的电离', '化学反应原理/盐类的水解', '化学反应原理/沉淀溶解平衡'],
    organic: ['有机化学基础'], equilibrium: ['化学反应原理/化学平衡'],
    structure: ['物质结构与性质'], experiment: ['化学实验基础'],
    electro: ['化学反应原理/原电池', '化学反应原理/化学电源', '化学反应原理/电解池', '化学反应原理/金属的电化学腐蚀与防护']
  };
  globalThis.ChemistryQuery = { under, match };
  if (typeof document === 'undefined') return;

  const root = document.getElementById('chem-app');
  if (!root) return;
  const $ = selector => root.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const leaf = path => path.split('/').pop();
  const encodePath = path => path.split('/').map(encodeURIComponent).join('/');
  const questionUrl = record => new URL('reader.html#' + encodeURIComponent(record.key), document.baseURI).href;
  const isLive = false;
  const storageKey = 'chemistry-packed-reader-v1';
  const defaults = () => ({ selected: [], open: [], query: '', type: '', scope: 'all', batch: '', paper: '', quick: '', applied: null, current: null, page: 1, view: 'library', focus: '', topicQuery: '', showEmpty: false, scroll: 0 });
  let state = defaults(), catalog = null, children = new Map(), counts = new Map(), primary = new Map(), modules = [], paperList = [];
  let busy = false, initialized = false, lastResults = '', frameObserver = null, scrollTimer = null, restoreScroll = false;

  function save() {
    try { localStorage.setItem(storageKey, JSON.stringify({ version: 2, state: { ...state, scroll: window.scrollY } })); } catch (_) { /* Private browsing may disable local storage. */ }
  }
  function loadState() {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
      if (saved?.version === 2 && saved.state) {
        state = { ...defaults(), ...saved.state };
        state.selected = Array.isArray(state.selected) ? state.selected.filter(p => typeof p === 'string') : [];
        state.open = Array.isArray(state.open) ? state.open.filter(p => typeof p === 'string') : [];
        if (!['library', 'graph', 'overview'].includes(state.view)) state.view = 'library';
        restoreScroll = true;
      }
    } catch (_) { state = defaults(); }
    if (document.body.dataset.initialView === 'overview') state.view = 'overview';
    const params = new URLSearchParams(location.hash.slice(1));
    if (params.has('category') || params.has('search') || params.has('quick')) readHash(params);
  }
  function criteria() {
    return { selected: [...state.selected], query: state.query.trim(), type: state.type, scope: state.scope, batch: state.batch, paper: state.paper, quick: state.quick };
  }
  function hasCriteria(c) { return c && (c.selected.length || c.query || c.type || c.batch || c.paper || c.quick); }
  function readHash(params) {
    state = { ...defaults(), selected: params.get('category') ? [params.get('category')] : [], query: params.get('search') || '', quick: quickPaths[params.get('quick')] ? params.get('quick') : '' };
    for (const path of state.selected) {
      const parts = path.split('/');
      for (let i = 1; i < parts.length; i++) state.open.push(parts.slice(0, i).join('/'));
    }
    state.applied = criteria();
  }
  function fillSelect(selector, items, label, value) {
    const select = $(selector);
    const missing = value && !items.some(([v]) => v === value);
    select.innerHTML = `<option value="">${esc(label)}</option>` + items.map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join('') + (missing ? `<option value="${esc(value)}">${esc(value)}（当前未收录）</option>` : '');
    select.value = value;
  }
  function syncInputs() {
    $('.cw-search input').value = state.query;
    $('#topic-search').value = state.topicQuery;
    $('#show-empty').checked = state.showEmpty;
    $('#cw-scope').value = state.scope;
    if (catalog) {
      fillSelect('#cw-type', [...new Set(catalog.records.map(r => r.question_type).filter(Boolean))].map(t => [t, t]), '全部题型', state.type);
      fillSelect('#cw-batch', catalog.batches.map(b => [b, b]), '全部批次', state.batch);
      fillSelect('#cw-paper', paperList.filter(p => !state.batch || p.batch === state.batch).map(p => [p.key, p.batch + ' · ' + p.label]), '全部试卷', state.paper);
    }
  }
  function index(data) {
    modules = data.taxonomy.filter(p => !p.includes('/'));
    children = new Map(data.taxonomy.map(p => [p, []]));
    counts = new Map(data.taxonomy.map(p => [p, 0]));
    primary = new Map(data.taxonomy.map(p => [p, 0]));
    const papers = new Map();
    for (const path of data.taxonomy) if (path.includes('/')) children.get(path.slice(0, path.lastIndexOf('/')))?.push(path);
    for (const record of data.records) {
      record.tags = [...new Set([record.main, ...(record.related || []), ...(record.subquestions || []).flatMap(s => s.topics || [])])];
      record.related ||= []; record.subquestions ||= [];
      record.searchText = [record.key, record.id, record.title, record.paper_label, record.text, ...record.tags, ...record.subquestions.map(s => s.focus || '')].join(' ').toLowerCase();
      const relatedPaths = new Set();
      for (const tag of record.tags) {
        const parts = tag.split('/');
        for (let d = 1; d <= parts.length; d++) relatedPaths.add(parts.slice(0, d).join('/'));
      }
      for (const path of relatedPaths) counts.set(path, (counts.get(path) || 0) + 1);
      const parts = record.main.split('/');
      for (let d = 1; d <= parts.length; d++) {
        const path = parts.slice(0, d).join('/'); primary.set(path, (primary.get(path) || 0) + 1);
      }
      const key = record.batch + ':' + record.paper_id;
      if (!papers.has(key)) papers.set(key, { key, batch: record.batch, id: record.paper_id, label: record.paper_label, count: 0 });
      papers.get(key).count++;
    }
    paperList = [...papers.values()];
  }
  function renderTree() {
    if (!catalog) return;
    const words = state.topicQuery.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const visible = new Set();
    for (const path of catalog.taxonomy) {
      if (!state.showEmpty && !counts.get(path) && !state.selected.includes(path)) continue;
      if (words.length && !words.every(w => path.toLowerCase().includes(w))) continue;
      const parts = path.split('/');
      for (let d = 1; d <= parts.length; d++) visible.add(parts.slice(0, d).join('/'));
    }
    function node(path) {
      if (!visible.has(path)) return '';
      const nested = (children.get(path) || []).filter(p => visible.has(p));
      const open = words.length > 0 || state.open.includes(path);
      return `<div class="cw-module"><div class="cw-topicrow" data-active="${state.selected.includes(path)}">${nested.length ? `<button type="button" class="cw-toggle" data-open="${esc(path)}" aria-label="${open ? '收起' : '展开'}${esc(leaf(path))}" aria-expanded="${Boolean(open)}">${open ? '⌄' : '›'}</button>` : '<span></span>'}<label class="cw-topiclabel"><input type="checkbox" data-topic="${esc(path)}" ${state.selected.includes(path) ? 'checked' : ''}><span>${esc(leaf(path))}</span></label></div>${open && nested.length ? `<div class="cw-topic-children">${nested.map(node).join('')}</div>` : ''}</div>`;
    }
    $('.cw-tree').innerHTML = modules.map(node).join('') || '<p class="cw-topic-empty">没有找到这个知识点。</p>';
    root.querySelectorAll('[data-topic]').forEach(input => { input.indeterminate = !input.checked && state.selected.some(t => under(t, input.dataset.topic)); });
  }
  function renderSelected() {
    $('.cw-selected').innerHTML = state.selected.length ? '<span class="cw-selection-note">已选</span>' + state.selected.map(p => `<button type="button" class="cw-chip" data-remove="${esc(p)}" aria-label="移除${esc(leaf(p))}"><span>${esc(leaf(p))}</span> ×</button>`).join('') : '<span class="cw-selection-note">尚未选择知识点</span>';
    if (state.quick) $('.cw-selected').insertAdjacentHTML('beforeend', '<span class="cw-chip">专题入口条件</span>');
  }
  function empty(title, detail) { return `<div class="cw-empty"><div class="cw-empty-icon">化</div><h2>${esc(title)}</h2><p>${esc(detail)}</p></div>`; }
  function hitExplanation(record) {
    const selected = state.applied?.selected || [];
    const paths = selected.length ? selected : [record.main];
    return paths.map(path => {
      const parts = [];
      if (under(record.main, path)) parts.push('主知识点');
      if (record.related.some(t => under(t, path))) parts.push('相关知识点');
      const questions = record.subquestions.filter(s => s.topics.some(t => under(t, path))).map(s => s.locator);
      if (questions.length) parts.push('小问：' + [...new Set(questions)].join('、'));
      return leaf(path) + '：' + (parts.join('；') || '知识点标注');
    }).map(esc).join('<br>');
  }
  function prepareFrame() {
    const frame = $('#question-frame');
    if (!frame) return;
    frame.addEventListener('load', () => {
      try {
        const doc = frame.contentDocument;
        if (!doc?.body) return;
        // Normalize the reading layout in the preview only, preserving original files.
        doc.querySelectorAll('.original details').forEach(detail => {
          const summary = detail.querySelector('summary')?.textContent || '';
          if (/题干|配图|原题/.test(summary) && !/答案|解析/.test(summary)) detail.open = true;
        });
        doc.querySelectorAll('.original').forEach(original => {
          const firstAnswer = [...original.children].find(node => /^H[23]$/.test(node.tagName) && /^(原答案|原解析|答案|解析)$/.test(node.textContent.trim()));
          if (!firstAnswer) return;
          const answer = doc.createElement('details');
          const summary = doc.createElement('summary'); summary.textContent = '查看答案与解析'; answer.appendChild(summary);
          let node = firstAnswer;
          original.insertBefore(answer, firstAnswer);
          while (node) { const next = node.nextSibling; answer.appendChild(node); node = next; }
        });
        const style = doc.createElement('style');
        style.textContent = 'body{background:white!important;margin:0!important;font-size:16px!important;line-height:1.9!important}main{max-width:none!important;margin:0!important;padding:0 4px 24px!important}.back{display:none!important}h1{display:none!important}.card,.panel{border:0!important;padding:0!important;margin:12px 0!important}.original img{max-width:100%!important;height:auto!important}table{max-width:100%}a{overflow-wrap:anywhere}details{margin:16px 0}.original{line-height:1.95!important}';
        doc.head.appendChild(style);
        doc.querySelectorAll('a').forEach(a => { a.target = '_blank'; a.rel = 'noopener'; });
        const resize = () => { const height = Math.max(680, Math.ceil(doc.body.getBoundingClientRect().height) + 24); if (Math.abs(parseInt(frame.style.height || '0', 10) - height) > 3) frame.style.height = Math.min(height, 120000) + 'px'; };
        resize();
        frameObserver?.disconnect(); frameObserver = new ResizeObserver(resize); frameObserver.observe(doc.body);
      } catch (_) { /* Local-file isolation: the original page remains readable in its frame. */ }
    });
  }
  function renderResults() {
    const signature = JSON.stringify([catalog?.version, state.applied, state.page, state.current]);
    const pending = state.applied && JSON.stringify(criteria()) !== JSON.stringify(state.applied);
    const notice = pending ? '<span class="cw-pending">条件已更改，点击检索后更新</span>' : '<span>点击题目，右侧查看完整内容</span>';
    if (signature === lastResults) { const hint = $('.cw-results-top'); if (hint) hint.lastElementChild.outerHTML = notice; return; }
    frameObserver?.disconnect(); frameObserver = null;
    if (!catalog) { $('.cw-content').innerHTML = empty('正在读取题库', '稍候即可按知识点检索。'); return; }
    if (!hasCriteria(state.applied)) {
      $('.cw-content').innerHTML = empty('选好知识点，再开始检索', '从左侧逐层展开，勾选需要的知识点，也可以直接搜索。');
      lastResults = signature; return;
    }
    const records = catalog.records.filter(r => match(r, state.applied));
    if (!records.length) {
      $('.cw-content').innerHTML = `<div class="cw-results-top"><span>没有符合条件的题目</span>${notice}</div>` + empty('暂时没有同时满足条件的题', '可以移除一个知识点，或调整条件后重新检索。');
      lastResults = signature; return;
    }
    const pageSize = 20, pageCount = Math.ceil(records.length / pageSize);
    state.page = Math.min(Math.max(Number(state.page) || 1, 1), pageCount);
    const page = records.slice((state.page - 1) * pageSize, state.page * pageSize);
    const record = page.find(r => r.key === state.current) || page[0]; state.current = record.key;
    const url = questionUrl(record);
    $('.cw-content').innerHTML = `<div class="cw-results-top"><span>找到 ${records.length} 道整题</span>${notice}</div><div class="cw-workbench"><div class="cw-result-list" aria-label="检索结果">${page.map(r => `<button type="button" class="cw-result-button" data-question="${esc(r.key)}" aria-pressed="${r.key === record.key}"><div class="cw-result-type">${esc(r.batch)} · ${esc(r.id)}${r.question_type ? ' · ' + esc(r.question_type) : ''}</div><div class="cw-result-title">${esc(r.title)}</div><div class="cw-result-excerpt">${esc(r.paper_label)} · 第${esc(r.number)}题</div><div class="cw-result-tags">${r.tags.slice(0, 3).map(t => `<span>${esc(leaf(t))}</span>`).join('')}</div></button>`).join('')}</div><article class="cw-reader"><div class="cw-reader-head">${esc(record.batch)} / ${esc(record.paper_label)} / 第${esc(record.number)}题</div><h2>${esc(record.title)}</h2><div class="cw-match-info">知识点命中位置<br>${hitExplanation(record)}</div><div class="cw-reader-links"><a href="${esc(url)}" target="_blank" rel="noopener">单独打开完整题目 ↗</a><span class="cw-tiny">原答案与原解析保留</span></div><iframe id="question-frame" class="cw-reader-frame" title="${esc(record.title)} · 完整题目" sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" src="about:blank"></iframe></article></div><div class="cw-pagination"><span>第 ${state.page} / ${pageCount} 页 · 每页最多 ${pageSize} 题</span><button type="button" class="cw-button" data-page="-1" ${state.page === 1 ? 'disabled' : ''}>上一页</button><button type="button" class="cw-button" data-page="1" ${state.page === pageCount ? 'disabled' : ''}>下一页</button></div>`;
    prepareFrame(); window.ChemPacked.preview(record.key, $('#question-frame')); lastResults = JSON.stringify([catalog.version, state.applied, state.page, state.current]);
  }
  function renderCoverage() {
    $('.cw-coverage-grid').innerHTML = modules.map(path => `<div class="cw-coverage-item"><span>${esc(path)}</span><span class="cw-coverage-status">${counts.get(path) || 0} 道相关整题</span></div>`).join('');
  }
  function renderGraph() {
    if (!catalog) return;
    if (!counts.has(state.focus)) state.focus = state.selected.find(p => counts.has(p)) || (counts.has('化学反应原理/原电池') ? '化学反应原理/原电池' : modules[0]);
    const focus = state.focus, neighbors = new Map();
    for (const record of catalog.records) {
      if (!record.tags.some(t => under(t, focus))) continue;
      for (const path of record.tags) if (!under(path, focus) && !under(focus, path)) neighbors.set(path, (neighbors.get(path) || 0) + 1);
    }
    const nodes = [...neighbors].sort((a, b) => b[1] - a[1]).slice(0, 6);
    const positions = [[21, 18], [79, 18], [84, 53], [73, 85], [27, 85], [16, 53]];
    $('.cw-graph-view').innerHTML = `<div class="cw-breadcrumb">题库首页 / 知识关联</div><div class="cw-graph-header"><div><h1>看看知识点之间的联系。</h1><p class="cw-intro">点击外围知识点，查看它周围的关联。</p></div><button type="button" class="cw-button" data-action="back-search">返回检索</button></div><label class="cw-graph-query">定位知识点<select id="graph-topic" aria-label="关联图知识点">${catalog.taxonomy.filter(p => counts.get(p)).map(p => `<option value="${esc(p)}" ${p === focus ? 'selected' : ''}>${esc(p.replaceAll('/', ' › '))}</option>`).join('')}</select></label><div class="cw-map" style="height:420px" aria-label="${esc(leaf(focus))}的知识关联图"><svg class="cw-map-lines" aria-hidden="true">${nodes.map((n, i) => `<line x1="50%" y1="48%" x2="${positions[i][0]}%" y2="${positions[i][1]}%"></line>`).join('')}</svg><button type="button" class="cw-map-node cw-center" style="left:50%;top:48%" data-focus="${esc(focus)}">${esc(leaf(focus))}</button>${nodes.map(([path, n], i) => `<button type="button" class="cw-map-node" data-focus="${esc(path)}" style="left:${positions[i][0]}%;top:${positions[i][1]}%">${esc(leaf(path))}<br><span class="cw-tiny">${n} 道共同整题</span></button>`).join('')}</div><div class="cw-graph-detail"><span>当前知识点：${esc(leaf(focus))}${nodes.length ? '' : ' · 暂无跨知识点关联'}</span><button type="button" class="cw-button cw-primary" data-action="add-focus">${state.selected.some(p => under(focus, p)) ? '已加入检索条件' : '加入检索条件'}</button></div><p class="cw-tiny">连线表示知识点在同一道整题中共同出现，不代表先修顺序；不同小问也可能分别命中。</p><p class="cw-footnote">${state.selected.length ? '已选：' + state.selected.map(leaf).map(esc).join(' ＋ ') : '可以逐个加入知识点，再返回检索。'}</p>`;
  }
  function renderOverview() {
    if (!catalog) return;
    $('.cw-overview-view').innerHTML = `<div class="cw-breadcrumb">题库首页 / 题库概况与来源</div><h1>需要时，再查看整体情况。</h1><p class="cw-intro">题目总量、各模块收录情况与试卷来源集中放在这里。</p><div class="cw-summary-grid"><div><b>${catalog.records.length}</b><span class="cw-tiny">道完整题目</span></div><div><b>${paperList.length}</b><span class="cw-tiny">套试卷记录</span></div><div><b>${catalog.batches.length}</b><span class="cw-tiny">个入库批次</span></div></div><div class="cw-table-wrap"><table class="cw-stat-table"><thead><tr><th>模块</th><th>主类别整题</th><th>全部相关整题</th></tr></thead><tbody>${modules.map(p => `<tr><td>${esc(p)}</td><td>${primary.get(p) || 0}</td><td>${counts.get(p) || 0}</td></tr>`).join('')}</tbody></table></div><p class="cw-footnote">相关题包含下级知识点和小问。同一题可以涉及多个模块，各模块题数不能直接相加。</p><details class="cw-coverage"><summary>查看全部试卷来源</summary><div class="cw-table-wrap"><table class="cw-stat-table"><thead><tr><th>批次</th><th>试卷</th><th>题数</th></tr></thead><tbody>${paperList.map(p => `<tr><td>${esc(p.batch)}</td><td><button class="cw-button cw-quiet" type="button" data-paper="${esc(p.key)}">${esc(p.id + ' ' + p.label)}</button></td><td>${p.count}</td></tr>`).join('')}</tbody></table></div></details><p class="cw-footnote"><a href="说明.html" target="_blank" rel="noopener">完整文字概况</a> · <a href="说明.html" target="_blank" rel="noopener">阅读说明</a> · <a href="说明.html" target="_blank" rel="noopener">维护说明</a></p>`;
  }
  function renderView() {
    $('.cw-library-view').hidden = state.view !== 'library'; $('.cw-graph-view').hidden = state.view !== 'graph'; $('.cw-overview-view').hidden = state.view !== 'overview';
    root.querySelectorAll('[data-view]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.view === state.view)));
    if (state.view === 'graph') renderGraph(); if (state.view === 'overview') renderOverview();
  }
  function render() { renderTree(); renderSelected(); renderResults(); renderCoverage(); renderView(); }
  function status(error) {
    const label = $('#monitor-status');
    label.textContent = error ? '读取新数据遇到问题，保留上次完整题库：' + error : isLive ? '实时监测中 · 分类数据更新：' + catalog.updated + '（北京时间）' : catalog.records.length + '道整题 · 原题与分类来源保留';
    label.classList.toggle('problem', Boolean(error));
    const address = window.CHEM_BANK_LIVE?.url;
    if (!isLive && /^http:\/\/127\.0\.0\.1:\d+\/$/.test(address || '')) { $('#live-link').href = address + encodeURIComponent('阅读入口.html'); $('#live-link').hidden = false; }
  }
  function apply(data) {
    if (!data || !Array.isArray(data.records) || !Array.isArray(data.taxonomy) || !Array.isArray(data.batches)) throw Error('题库数据格式不完整');
    if (data.error && catalog) { status(data.error); return; }
    if (!catalog || data.version !== catalog.version) {
      catalog = data; index(data); if (!initialized) loadState(); syncInputs(); lastResults = ''; render();
      if (!initialized && restoreScroll) requestAnimationFrame(() => window.scrollTo(0, state.scroll || 0));
      initialized = true;
    }
    status(data.error);
  }
  async function refresh() {
    if (!isLive || busy || document.hidden) return;
    busy = true;
    try {
      const url = new URL('api/catalog', document.baseURI); url.searchParams.set('version', catalog?.version || '');
      const response = await fetch(url, { cache: 'no-store' }); if (!response.ok) throw Error('暂时无法连接监测服务');
      const data = await response.json(); if (!data.monitoring) throw Error('请通过“更新题库”打开实时页面');
      if (data.unchanged) status(data.error); else apply(data);
    } catch (error) { if (catalog) status(error.message); else $('#monitor-status').textContent = '无法读取题库：' + error.message; }
    finally { busy = false; }
  }
  function search() {
    state.query = $('.cw-search input').value; state.type = $('#cw-type').value; state.scope = $('#cw-scope').value; state.batch = $('#cw-batch').value; state.paper = $('#cw-paper').value;
    state.applied = criteria(); state.current = null; state.page = 1; state.view = 'library'; lastResults = ''; render(); save();
  }
  root.addEventListener('click', event => {
    const open = event.target.closest('[data-open]'); if (open) { const path = open.dataset.open; state.open = state.open.includes(path) ? state.open.filter(p => p !== path) : [...state.open, path]; renderTree(); save(); return; }
    const remove = event.target.closest('[data-remove]'); if (remove) { state.selected = state.selected.filter(p => p !== remove.dataset.remove); renderTree(); renderSelected(); renderResults(); save(); return; }
    const question = event.target.closest('[data-question]'); if (question) { state.current = question.dataset.question; renderResults(); save(); return; }
    const page = event.target.closest('[data-page]'); if (page && !page.disabled) { state.page += Number(page.dataset.page); state.current = null; renderResults(); save(); return; }
    const view = event.target.closest('[data-view]'); if (view) { state.view = view.dataset.view; if (state.view === 'graph' && state.selected.length) state.focus = state.selected[0]; renderView(); save(); return; }
    const focus = event.target.closest('[data-focus]'); if (focus) { state.focus = focus.dataset.focus; renderGraph(); save(); return; }
    const paper = event.target.closest('[data-paper]'); if (paper) { state = { ...defaults(), paper: paper.dataset.paper }; syncInputs(); search(); return; }
    const action = event.target.closest('[data-action]')?.dataset.action; if (!action) return;
    if (action === 'search') { search(); return; }
    if (action === 'clear') { state = { ...defaults(), open: state.open }; syncInputs(); lastResults = ''; render(); }
    if (action === 'collapse') { state.open = []; state.topicQuery = ''; $('#topic-search').value = ''; renderTree(); }
    if (action === 'overview') { state.view = 'overview'; renderView(); }
    if (action === 'back-search') { state.view = 'library'; renderView(); }
    if (action === 'add-focus') { if (!state.selected.some(p => under(state.focus, p))) { state.selected = state.selected.filter(p => !under(p, state.focus)); state.selected.push(state.focus); } renderTree(); renderSelected(); renderResults(); renderGraph(); }
    save();
  });
  root.addEventListener('change', event => {
    if (event.target.matches('[data-topic]')) { const path = event.target.dataset.topic; if (event.target.checked) { state.selected = state.selected.filter(p => !under(p, path) && !under(path, p)); state.selected.push(path); } else state.selected = state.selected.filter(p => p !== path); state.quick = ''; renderTree(); renderSelected(); renderResults(); save(); return; }
    if (event.target.id === 'show-empty') { state.showEmpty = event.target.checked; renderTree(); save(); }
    if (event.target.id === 'graph-topic') { state.focus = event.target.value; renderGraph(); save(); }
    if (event.target.matches('#cw-type,#cw-scope,#cw-batch,#cw-paper')) { state.type = $('#cw-type').value; state.scope = $('#cw-scope').value; const batch = $('#cw-batch').value; if (batch !== state.batch) { state.paper = ''; state.batch = batch; syncInputs(); } else state.paper = $('#cw-paper').value; renderResults(); save(); }
  });
  $('.cw-search').addEventListener('submit', event => { event.preventDefault(); search(); });
  $('.cw-search input').addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); search(); } });
  $('.cw-search input').addEventListener('input', event => { state.query = event.target.value; renderResults(); save(); });
  $('#topic-search').addEventListener('input', event => { state.topicQuery = event.target.value; renderTree(); save(); });
  window.addEventListener('hashchange', () => { readHash(new URLSearchParams(location.hash.slice(1))); syncInputs(); lastResults = ''; render(); save(); });
  window.addEventListener('pagehide', save);
  window.addEventListener('scroll', () => { clearTimeout(scrollTimer); scrollTimer = setTimeout(save, 180); }, { passive: true });
  if (window.CHEM_BANK) { try { apply(window.CHEM_BANK); } catch (error) { $('#monitor-status').textContent = '无法读取题库：' + error.message; } }
  refresh();
  if (isLive) { setInterval(refresh, 2000); document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); }); }
})();
