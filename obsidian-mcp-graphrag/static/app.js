'use strict';

/* ============================================================
   Knowledge Base Web UI — Main Application
   ============================================================ */

// ─── DOM Refs ───────────────────────────────────────────────
const q = document.getElementById('q');
const output = document.getElementById('output');
const cancelBtn = document.getElementById('cancelBtn') || (() => {
  const btn = document.createElement('button');
  btn.id = 'cancelBtn';
  btn.textContent = '取消';
  btn.style.display = 'none';
  q.parentNode.appendChild(btn);
  return btn;
})();

// ─── State ──────────────────────────────────────────────────
let currentAbortController = null;
let isSearching = false;
let graphChart = null;
let sectorChart = null;
let videoFrames = [];
let conversations = [];
let lastSources = [];
let lastStrategy = '';

const CONV_KEY = 'kb_conversations';

// ─── Utility ────────────────────────────────────────────────
function esc(s) {
  if (!s && s !== 0) return '';
  const div = document.createElement('div');
  div.appendChild(document.createTextNode(String(s)));
  return div.innerHTML;
}

// ─── Markdown Renderer ─────────────────────────────────────
function renderMarkdown(text) {
  if (!text) return '';
  let html = esc(text);

  // Code blocks (must come before inline code)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const langAttr = lang ? ` class="language-${esc(lang)}"` : '';
    return `<pre><code${langAttr}>${esc(code.trim())}</code></pre>`;
  });

  // Headers
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Links [text](url)
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

  // Numbered lists
  html = html.replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ol>$&</ol>');

  // Unordered lists
  html = html.replace(/^[-*]\s+(.+)$/gm, '<li>$1</li>');

  // Line breaks (double newline = paragraph)
  html = html.replace(/\n\n+/g, '</p><p>');
  html = html.replace(/\n/g, '<br>');

  return `<p>${html}</p>`;
}

// ─── Skeleton Loading ──────────────────────────────────────
function showSkeleton() {
  output.innerHTML = `
    <div class="skeleton-container">
      <div class="skeleton-card"><div class="skeleton-line" style="width:60%"></div><div class="skeleton-line"></div><div class="skeleton-line" style="width:80%"></div></div>
      <div class="skeleton-card"><div class="skeleton-line" style="width:45%"></div><div class="skeleton-line"></div><div class="skeleton-line" style="width:70%"></div></div>
      <div class="skeleton-card"><div class="skeleton-line" style="width:55%"></div><div class="skeleton-line"></div><div class="skeleton-line" style="width:90%"></div></div>
    </div>
    <div class="typing-cursor">|</div>`;
  cancelBtn.style.display = 'inline-block';
}

function hideSkeleton() {
  const skeletons = output.querySelectorAll('.skeleton-container, .typing-cursor');
  skeletons.forEach(el => el.remove());
  cancelBtn.style.display = 'none';
}

// ─── SSE Streaming Search ──────────────────────────────────
async function doSearch() {
  const query = q.value.trim();
  if (!query) return;
  if (isSearching && currentAbortController) {
    currentAbortController.abort();
  }

  currentAbortController = new AbortController();
  isSearching = true;

  showSkeleton();

  let answerHTML = '';
  let sourcesData = [];

  function updateAnswerStream(html) {
    hideSkeleton();
    let container = output.querySelector('.answer-stream-container');
    if (!container) {
      container = document.createElement('div');
      container.className = 'answer-stream-container';
      container.innerHTML = '<div class="answer-content"></div>';
      output.insertBefore(container, output.firstChild);
    }
    const content = container.querySelector('.answer-content');
    if (content) {
      content.innerHTML = renderMarkdown(html) + '<span class="typing-cursor">|</span>';
    }
  }

  try {
    const response = await fetch('/query/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, history: getRecentHistory() }),
      signal: currentAbortController.signal
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data: ')) continue;
        try {
          const data = JSON.parse(trimmed.slice(6));
          switch (data.type) {
            case 'token':
              answerHTML += data.data;
              updateAnswerStream(answerHTML);
              break;
            case 'sources':
              sourcesData = data.data || [];
              break;
            case 'done':
              const meta = data.data || {};
              lastSources = meta.results || sourcesData;
              lastStrategy = meta.strategy || '';
              renderFinal(answerHTML, meta.results || sourcesData, meta.source_type || 'knowledge', meta.strategy || '', query);
              // Save conversation with answer
              saveConversation(query, answerHTML);
              break;
            case 'error':
              showError(data.data);
              break;
          }
        } catch (e) {
          continue;
        }
      }
    }

    // Fallback: if done event was never received but we have answer
    if (answerHTML && !output.querySelector('.final-content')) {
      renderFinal(answerHTML, sourcesData, 'knowledge', '', query);
    }
  } catch (e) {
    if (e.name === 'AbortError') return;
    showError(e.message);
  } finally {
    isSearching = false;
    hideSkeleton();
    cancelBtn.style.display = 'none';
  }
}

function renderFinal(answer, sources, sourceType, strategy, query) {
  hideSkeleton();
  // Remove streaming container if exists
  const streamContainer = output.querySelector('.answer-stream-container');
  if (streamContainer) {
    streamContainer.remove();
  }

  const srcLabel = sourceType === 'web' ? '🌐 网络搜索' : sourceType === 'hybrid' ? '📚+🌐 知识库&网络' : '📚 知识库';
  const sourcesBlock = sources && sources.length
    ? `<div class="sources-block">
        <h4 style="color:#6c63ff;font-size:13px;margin-bottom:8px">📋 知识库来源 (${sources.length}) <span class="toggle-sources-btn" style="color:#888;font-size:12px;cursor:pointer;margin-left:8px" onclick="toggleSources()">展开</span></h4>
        <div class="sources-list" style="display:none">${renderSources(sources)}</div>
       </div>`
    : '';

  output.innerHTML = `
    <div class="final-content">
      <div class="answer-card" style="background:linear-gradient(135deg,#1a1a2e,#16213e);border-radius:12px;padding:24px;border:1px solid #2a2a4a;margin-bottom:16px">
        <div style="color:#6c63ff;font-size:13px;margin-bottom:12px;display:flex;align-items:center;gap:6px">
          🤖 AI 回答 <span style="font-size:11px;padding:2px 8px;border-radius:4px;background:#2a2a4a;color:#aaa">${srcLabel}</span>
        </div>
        <div class="answer-text" style="color:#e0e0e0;font-size:15px;line-height:1.8;white-space:pre-wrap">${renderMarkdown(answer)}</div>
      </div>
      ${sourcesBlock}
    </div>`;
}

function renderSources(sources) {
  if (!sources || !sources.length) return '<em>无来源</em>';
  return sources.map(s => {
    const page = s.page || s.title || s.filename || '';
    const category = s.category || '';
    const score = s.score || s.relevance || '';
    const excerpt = s.excerpt || s.text || '';
    const source = s.source || 'wiki';
    const scoreDisplay = score ? (typeof score === 'number' ? (score * 100).toFixed(0) + '%' : score) : '';
    return `<div class="result-card" style="background:#1a1a2e;border-radius:10px;padding:16px;margin-bottom:12px;border-left:3px solid #6c63ff">
      <div style="color:#6c63ff;font-size:14px;margin-bottom:6px">
        📄 ${esc(page)}
        ${category ? `<span style="color:#555;margin-left:8px;font-size:12px">${esc(category)}</span>` : ''}
        ${scoreDisplay ? `<span style="float:right;color:#555;font-size:12px">相关度 ${scoreDisplay}</span>` : ''}
      </div>
      ${excerpt ? `<div style="color:#ccc;font-size:14px;line-height:1.7">${esc(excerpt)}</div>` : ''}
      <span style="display:inline-block;background:#16213e;color:#888;font-size:11px;padding:2px 8px;border-radius:4px;margin-top:6px">${esc(source)}</span>
    </div>`;
  }).join('');
}

function toggleSources() {
  const list = document.querySelector('.sources-list');
  const btn = document.querySelector('.toggle-sources-btn');
  if (!list) return;
  const show = list.style.display === 'none';
  list.style.display = show ? 'block' : 'none';
  if (btn) btn.textContent = show ? '收起' : '展开';
}

function showError(msg) {
  hideSkeleton();
  output.innerHTML = `<div class="error-msg">❌ ${esc(msg)}</div>`;
}

// ─── Conversation History ──────────────────────────────────
function getConversations() {
  try {
    const raw = localStorage.getItem(CONV_KEY);
    conversations = raw ? JSON.parse(raw) : [];
  } catch {
    conversations = [];
  }
  return conversations;
}

function saveConversation(query, answer) {
  getConversations();
  conversations.unshift({
    id: Date.now() + '_' + Math.random().toString(36).slice(2, 6),
    query,
    answer: answer ? answer.slice(0, 500) : '', // cap answer length
    timestamp: Date.now()
  });
  if (conversations.length > 50) conversations = conversations.slice(0, 50);
  try {
    localStorage.setItem(CONV_KEY, JSON.stringify(conversations));
  } catch {}
  renderHistory();
}

function getRecentHistory(n) {
  getConversations();
  // Return {query, answer} objects for context window
  return conversations.slice(0, n || 3).map(c => ({
    query: c.query || '',
    answer: c.answer || ''
  }));
}

function renderHistory() {
  const container = document.getElementById('historyList');
  if (!container) return;
  getConversations();
  if (!conversations.length) {
    container.innerHTML = '<div class="history-empty">暂无历史</div>';
    return;
  }
  container.innerHTML = conversations.map(c => {
    const time = new Date(c.timestamp);
    const timeStr = `${time.getHours().toString().padStart(2, '0')}:${time.getMinutes().toString().padStart(2, '0')}`;
    return `<div class="history-item" onclick="loadConversation('${c.id}')" data-id="${c.id}">
      <span class="history-q">${esc(c.query)}</span>
      <span class="history-time">${timeStr}</span>
    </div>`;
  }).join('');
}

function loadConversation(id) {
  getConversations();
  const item = conversations.find(c => c.id === id);
  if (item) {
    q.value = item.query;
    doSearch();
  }
}

function clearHistory() {
  conversations = [];
  try {
    localStorage.removeItem(CONV_KEY);
  } catch {}
  renderHistory();
}

// ─── Vision ─────────────────────────────────────────────────
function onImageSelected(e) {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(ev) {
    const preview = document.getElementById('imagePreview');
    const img = document.getElementById('selectedImage');
    const info = document.getElementById('imageInfo');
    const btn = document.getElementById('visionBtn');
    if (img && preview) {
      img.src = ev.target.result;
      preview.style.display = 'block';
    }
    if (info) info.textContent = file.name + ' (' + (file.size/1024).toFixed(0) + 'KB)';
    if (btn) btn.style.display = '';
  };
  reader.readAsDataURL(file);
}

async function doVision() {
  const fileInput = document.getElementById('imageInput');
  if (!fileInput || !fileInput.files.length) return;
  const formData = new FormData();
  formData.append('file', fileInput.files[0]);

  try {
    const res = await fetch('/vision', { method: 'POST', body: formData });
    const data = await res.json();
    output.innerHTML = `<div class="vision-result"><h4>🔍 视觉分析</h4><p>${esc(data.answer || data.description || data.result || JSON.stringify(data))}</p></div>`;
  } catch (e) {
    showError('视觉分析失败: ' + e.message);
  }
}

// ─── Video ──────────────────────────────────────────────────
function onVideoSelected(e) {
  const file = e.target.files[0];
  if (!file) return;
  const video = document.getElementById('videoPlayer');
  const controls = document.getElementById('videoControls');
  const goBtn = document.getElementById('videoGoBtn');
  const cancelBtn = document.getElementById('videoCancelBtn');
  if (video && controls) {
    video.src = URL.createObjectURL(file);
    controls.style.display = 'flex';
  }
  if (goBtn) goBtn.style.display = '';
  if (cancelBtn) cancelBtn.style.display = '';
}

function cancelVideo() {
  const video = document.getElementById('videoPlayer');
  const controls = document.getElementById('videoControls');
  const input = document.getElementById('videoInput');
  const goBtn = document.getElementById('videoGoBtn');
  const cancelBtn = document.getElementById('videoCancelBtn');
  if (video) { video.pause(); video.src = ''; }
  if (controls) controls.style.display = 'none';
  if (input) input.value = '';
  if (goBtn) goBtn.style.display = 'none';
  if (cancelBtn) cancelBtn.style.display = 'none';
  videoFrames = [];
}

function processVideo() {
  const videoEl = document.getElementById('videoPlayer');
  if (!videoEl || !videoEl.src) return;

  const progress = document.getElementById('videoProgress');
  const bar = document.getElementById('videoProgressFill');
  const text = document.getElementById('videoProgressText');
  const frDiv = document.getElementById('videoFrameResults');

  if (progress) progress.style.display = 'block';
  if (bar) bar.style.width = '0%';
  if (text) text.textContent = '正在处理视频...';
  if (frDiv) frDiv.innerHTML = '';

  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  const duration = videoEl.duration || 30;
  const maxFrames = Math.min(12, Math.ceil(duration / 3));
  const frameInterval = duration / (maxFrames + 1);
  const formData = new FormData();

  let captured = 0;
  let currentTime = frameInterval;

  function captureNext() {
    if (captured >= maxFrames) {
      if (captured === 0) {
        if (text) text.textContent = '❌ 未提取到有效帧';
        return;
      }
      formData.append('query', '请综合分析这段视频的完整内容。包括：主题、场景、人物/物体、关键动作、氛围变化');
      formData.append('max_tokens', '2048');

      if (text) text.textContent = `⏳ ${captured}帧发给AI分析中...`;
      if (bar) bar.style.width = '50%';

      fetch('/video-analysis', { method: 'POST', body: formData })
        .then(r => r.json())
        .then(data => {
          if (bar) bar.style.width = '100%';
          if (data.error) {
            if (text) text.textContent = '❌ ' + data.error;
          } else {
            if (text) text.textContent = `✅ 分析完成 · ${captured}帧 · ${duration.toFixed(1)}s`;
            if (frDiv) {
              frDiv.innerHTML = '<div class="result-card"><div class="result-text">' + esc(data.answer || '(空)') + '</div></div>';
            }
          }
        })
        .catch(e => {
          if (text) text.textContent = '❌ 请求失败';
        });
      return;
    }

    videoEl.currentTime = Math.min(currentTime, duration - 0.1);
    videoEl.onseeked = function() {
      canvas.width = 320;
      const ratio = 320 / (videoEl.videoWidth || 640);
      canvas.height = Math.round((videoEl.videoHeight || 480) * ratio);
      ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(function(blob) {
        if (blob && blob.size > 500) {
          formData.append('images', blob, 'f' + captured + '.jpg');
          captured++;
          if (text) text.textContent = `帧 ${captured}/${maxFrames} @${currentTime.toFixed(1)}s`;
          if (bar) bar.style.width = (captured / maxFrames * 50) + '%';
        }
        currentTime += frameInterval;
        captureNext();
      }, 'image/jpeg', 0.6);
    };
    // Trigger seek
    videoEl.currentTime = Math.min(currentTime, duration - 0.1);
  }

  videoEl.pause();
  captureNext();
}

async function sendVideoFrames() {
  // sendVideoFrames is kept for compatibility; actual video processing
  // is done in processVideo() using FormData + canvas frames.
  // This function is called if processVideo needs to send pre-captured frames.
  try {
    const formData = new FormData();
    let frameCount = 0;
    for (const frame of videoFrames) {
      if (frame.blob) {
        formData.append('images', frame.blob, 'f' + frameCount + '.jpg');
        frameCount++;
      }
    }
    if (!frameCount) {
      showError('没有可分析的视频帧');
      return;
    }
    formData.append('query', '请综合分析这段视频的完整内容。包括：主题、场景、人物/物体、关键动作、氛围变化');
    formData.append('max_tokens', '2048');
    const res = await fetch('/video-analysis', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.error) {
      showError(data.error);
    } else {
      output.innerHTML = `<div class="video-result"><h4>🎬 视频分析</h4><p>${esc(data.answer || JSON.stringify(data))}</p></div>`;
    }
  } catch (e) {
    showError('视频分析失败: ' + e.message);
  }
}

// ─── Knowledge Graph ───────────────────────────────────────
function toggleGraph() {
  const panel = document.getElementById('graphPanel');
  if (!panel) return;
  const show = panel.style.display === 'none' || !panel.style.display;
  panel.style.display = show ? 'flex' : 'none';
  if (show) loadGraph();
}

async function loadGraph() {
  const container = document.getElementById('graphContainer');
  if (!container) return;

  try {
    const res = await fetch('/api/graph');
    const data = await res.json();

    if (!graphChart) {
      graphChart = echarts.init(container);
      window.addEventListener('resize', () => graphChart && graphChart.resize());
    }

    renderGraph(data);
  } catch (e) {
    container.innerHTML = `<div class="error-msg">图谱加载失败: ${esc(e.message)}</div>`;
  }
}

function renderGraph(data) {
  if (!graphChart) return;

  // Backend returns {nodes: [{id, name, symbolSize, category, itemStyle}], edges: [{source, target, label}]}
  const nodes = (data.nodes || []).map(n => ({
    id: n.id || n.name,
    name: n.name || n.id,
    symbolSize: Math.max(6, n.symbolSize || 10),
    category: n.category || 'unknown',
    itemStyle: n.itemStyle || { color: getCategoryColor(n.category) },
    label: { show: false }
  }));

  const edges = (data.edges || []).map(e => ({
    source: e.source || e.from,
    target: e.target || e.to,
    label: e.label || { show: false }
  }));

  const catSet = {};
  nodes.forEach(n => { if (!catSet[n.category]) catSet[n.category] = true; });
  const categories = Object.keys(catSet).map(c => ({
    name: c,
    itemStyle: { color: getCategoryColor(c) }
  }));

  const option = {
    backgroundColor: '#0d0d1a',
    tooltip: { trigger: 'item', formatter: '{b}' },
    animationDuration: 600,
    animationEasingUpdate: 'cubicInOut',
    series: [{
      type: 'graph',
      layout: 'force',
      force: { repulsion: 200, edgeLength: [60, 180], gravity: 0.12, layoutAnimation: true, friction: 0.6 },
      roam: true,
      draggable: true,
      data: nodes,
      edges: edges,
      lineStyle: { color: 'rgba(255,255,255,0.12)', curveness: 0.2, width: 0.7, opacity: 0.5 },
      label: { show: false },
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 1.5, color: 'rgba(255,255,255,0.4)', opacity: 1 },
        itemStyle: { opacity: 1, borderColor: 'rgba(255,255,255,0.7)', borderWidth: 2 },
        label: { show: true, fontSize: 12, fontWeight: '600', color: '#fff', backgroundColor: 'rgba(13,13,26,0.9)', padding: [4, 10], borderRadius: 4, distance: 10 }
      },
      blur: { itemStyle: { opacity: 0.08 }, lineStyle: { opacity: 0.02 }, label: { show: false } },
      lineStyle: { color: '#555', width: 1.5, curveness: 0.2 },
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 3, color: '#7ec8e3' }
      }
    }]
  };

  graphChart.setOption(option, true);
}

function getCategoryColor(cat) {
  const palette = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272', '#fc8452', '#9a60b4', '#ea7ccc'];
  return palette[Number(cat) % palette.length];
}

function resetGraph() {
  if (graphChart) graphChart.clear();
  loadGraph();
}

function filterGraph(keyword) {
  if (!graphChart) return;
  const kw = keyword.toLowerCase().trim();
  const option = graphChart.getOption();
  const nodes = option.series[0].data || [];
  const edges = option.series[0].edges || [];

  nodes.forEach(n => {
    if (!kw) {
      n.label = { show: true, color: '#ccc', fontSize: 11 };
      n.itemStyle = { opacity: 1, color: getCategoryColor(n.category || 0) };
    } else if ((n.name || '').toLowerCase().includes(kw)) {
      n.label = { show: true, color: '#ffd700', fontSize: 14, fontWeight: 'bold' };
      n.itemStyle = { opacity: 1, color: '#ffd700', shadowBlur: 10, shadowColor: '#ffd700' };
    } else {
      n.label = { show: false };
      n.itemStyle = { opacity: 0.15, color: getCategoryColor(n.category || 0) };
    }
  });

  edges.forEach(e => {
    if (!kw) {
      e.lineStyle = { opacity: 0.6, color: '#555', width: 1.5 };
    } else {
      const src = (nodes.find(n => n.id === e.source) || {}).name || '';
      const tgt = (nodes.find(n => n.id === e.target) || {}).name || '';
      if (src.toLowerCase().includes(kw) || tgt.toLowerCase().includes(kw)) {
        e.lineStyle = { opacity: 1, color: '#ffd700', width: 3 };
      } else {
        e.lineStyle = { opacity: 0.08, color: '#555', width: 1 };
      }
    }
  });

  graphChart.setOption(option, true);
}

function exportGraphImage() {
  if (!graphChart) return;
  const url = graphChart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#1a1a2e' });
  const a = document.createElement('a');
  a.href = url;
  a.download = 'knowledge-graph.png';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

// ─── Market Data ───────────────────────────────────────────
let currentMarketTab = 'indices';

function switchMarketTab(tab) {
  currentMarketTab = tab;
  document.querySelectorAll('.market-tab').forEach(el => {
    el.classList.toggle('active', el.dataset.tab === tab);
  });
  document.querySelectorAll('.market-tab-content').forEach(el => {
    el.style.display = el.id === `market-${tab}` ? 'block' : 'none';
  });

  if (tab === 'sectors') {
    fetchMarket().then(() => {
      setTimeout(() => { if (sectorChart) sectorChart.resize(); }, 200);
    });
  } else if (tab === 'limitup') {
    fetchLimitUp();
  } else if (tab === 'abnormal') {
    fetchAbnormal();
  } else if (tab === 'pick') {
    doStockPick();
  } else {
    fetchMarket();
  }
}

async function fetchMarket() {
  try {
    const res = await fetch('/market');
    const data = await res.json();
    renderMarket(data);
  } catch (e) {
    document.getElementById('market-indices').innerHTML = `<div class="error-msg">行情加载失败: ${esc(e.message)}</div>`;
  }
}

function renderMarket(data) {
  // Indices
  const indicesContainer = document.getElementById('market-indices');
  if (indicesContainer) {
    const indices = data.indices || [];
    if (!indices.length) {
      indicesContainer.innerHTML = '<div class="empty-data">暂无数据</div>';
    } else {
      const upCount = indices.filter(i => parseFloat(i.change_pct || 0) >= 0).length;
      const downCount = indices.filter(i => parseFloat(i.change_pct || 0) < 0).length;
      indicesContainer.innerHTML = `
        <div class="market-summary-bar">
          <span>📈 涨 <b class="up">${upCount}</b> 家</span>
          <span>📉 跌 <b class="down">${downCount}</b> 家</span>
          <span style="color:var(--text-muted);font-size:12px">${data.market_date || ''} ${data.market_time || ''}</span>
        </div>
        <div class="index-cards">
          ${indices.map(i => {
            const chg = parseFloat(i.change_pct || 0);
            const cls = chg >= 0 ? 'up' : 'down';
            return `<div class="index-card ${cls}">
              <div class="index-name">${esc(i.name || '')}</div>
              <div class="index-price">${esc(String(i.price || ''))}</div>
              <div class="index-change">${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%</div>
            </div>`;
          }).join('')}
        </div>`;
    }
  }

  // Sectors
  const sectors = data.sectors || [];
  renderSectorChart(sectors);
}

function renderSectorChart(sectors) {
  const container = document.getElementById('sectorChart');
  if (!container) return;

  // Also update the summary bar in the sectors panel
  const sectorPanel = document.getElementById('market-sectors');
  const existingBar = sectorPanel ? sectorPanel.querySelector('.sector-summary-bar') : null;

  if (!sectors || !sectors.length) {
    container.innerHTML = '<div class="empty-data">暂无板块数据</div>';
    if (sectorChart) { sectorChart.dispose(); sectorChart = null; }
    return;
  }

  const up = sectors.filter(s => parseFloat(s.change || 0) > 0);
  const down = sectors.filter(s => parseFloat(s.change || 0) < 0);
  const flat = sectors.filter(s => parseFloat(s.change || 0) === 0);

  // Summary bar
  const summaryHTML = `
    <div class="market-summary-bar">
      <span>📈 涨 <b class="up">${up.length}</b> 板块</span>
      <span>📉 跌 <b class="down">${down.length}</b> 板块</span>
      ${flat.length ? `<span>一 平 <b>${flat.length}</b></span>` : ''}
      <span style="color:var(--text-muted);font-size:12px">涨幅最大: <b style="color:#00d4aa">${up[0]?.name || '—'} ${up[0]?.change ? '+' + up[0].change + '%' : ''}</b></span>
    </div>`;
  if (existingBar) {
    existingBar.outerHTML = summaryHTML;
  } else if (sectorPanel) {
    const marketContent = sectorPanel.querySelector('.market-content');
    if (marketContent) {
      marketContent.insertAdjacentHTML('afterbegin', summaryHTML);
    }
  }

  if (!sectorChart) {
    sectorChart = echarts.init(container);
    window.addEventListener('resize', () => sectorChart && sectorChart.resize());
  }

  // Backend returns [{name, change}] - change is the pct change value
  const names = sectors.slice(0, 12).map(s => s.name || '');
  const values = sectors.slice(0, 12).map(s => parseFloat(s.change || 0));
  // Reverse for horizontal bar (last item at top)
  const revNames = names.slice().reverse();
  const revValues = values.slice().reverse();

  sectorChart.setOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: function(p) {
        return p[0].axisValue + '<br/>涨跌幅: ' + (p[0].value >= 0 ? '+' : '') + p[0].value.toFixed(2) + '%';
      }
    },
    grid: { left: '3%', right: '12%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'value',
      axisLabel: { formatter: '{value}%', color: '#aaa' },
      splitLine: { lineStyle: { color: '#2a2a4a' } }
    },
    yAxis: {
      type: 'category',
      data: revNames,
      axisLabel: { color: '#ccc', fontSize: 12, fontWeight: 'bold' }
    },
    series: [{
      type: 'bar',
      data: revValues.map(v => ({
        value: v,
        itemStyle: {
          color: v >= 0 ? new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: '#00d4aa' },
            { offset: 1, color: '#00a88a' }
          ]) : new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: '#ff6b6b' },
            { offset: 1, color: '#cc4444' }
          ]),
          borderRadius: [0, 4, 4, 0]
        }
      })),
      barMaxWidth: 22,
      label: {
        show: true,
        position: 'right',
        fontSize: 12,
        fontWeight: 'bold',
        color: '#bbb',
        formatter: function(p) { return (p.value >= 0 ? '+' : '') + p.value.toFixed(2) + '%'; }
      }
    }]
  }, true);
}

// ─── Limit Up ──────────────────────────────────────────────
async function fetchLimitUp() {
  try {
    const res = await fetch('/limit-up');
    const data = await res.json();
    renderLimitUp(data);
  } catch (e) {
    document.getElementById('market-limitup').innerHTML = `<div class="error-msg">涨停数据加载失败: ${esc(e.message)}</div>`;
  }
}

function renderLimitUp(data) {
  const container = document.getElementById('market-limitup');
  if (!container) return;

  // Backend returns: {limit_up: [{code,name,price,change,change_str,vol_ratio,amplitude,turnover,...}], top_gainers: [...]}
  const limitUp = data.limit_up || [];
  const topGainers = data.top_gainers || [];

  let html = '';
  if (limitUp.length) {
    html += `<div class="limitup-section">
      <h4>🔴 涨停股 (${limitUp.length})</h4>
      ${_buildStockTable(limitUp, true)}
    </div>`;
  }
  if (topGainers.length) {
    html += `<div class="limitup-section">
      <h4>🟠 热门涨幅 (${topGainers.length})</h4>
      ${_buildStockTable(topGainers, true)}
    </div>`;
  }
  if (!html) {
    html = '<div class="empty-data">暂无涨停数据</div>';
  }
  container.innerHTML = html;
}

function _buildStockTable(rows, showWatch) {
  if (!rows || !rows.length) return '<div class="empty-data">暂无数据</div>';

  const tableRows = rows.map(r => {
    const name = r.name || '';
    const code = r.code || '';
    const price = r.price || '--';
    const chg = typeof r.change === 'number' ? r.change : parseFloat(r.change_str || 0);
    const chgCls = chg >= 0 ? 'up' : 'down';
    const chgDisplay = r.change_str || (chg >= 0 ? '+' : '') + chg.toFixed(2) + '%';
    const turnover = typeof r.turnover === 'number' ? r.turnover.toFixed(1) + '%' : '--';
    const volRatio = typeof r.vol_ratio === 'number' ? r.vol_ratio.toFixed(2) : '--';
    const amplitude = typeof r.amplitude === 'number' ? r.amplitude.toFixed(1) + '%' : '--';
    const watchBtn = showWatch
      ? `<button class="watch-btn ${isWatched(code) ? 'watched' : ''}" data-code="${esc(code)}" data-name="${esc(name)}" data-price="${esc(price)}" data-change="${esc(chgDisplay)}">${isWatched(code) ? '★' : '☆'}</button>`
      : '';
    return `<tr>
      <td><b>${esc(name)}</b><br><span class="stock-code">${esc(code)}</span></td>
      <td>${esc(price)}</td>
      <td class="${chgCls}">${chgDisplay}</td>
      <td>${turnover}</td>
      <td>${volRatio}</td>
      <td>${amplitude}</td>
      ${showWatch ? `<td>${watchBtn}</td>` : ''}
    </tr>`;
  }).join('');

  return `<div class="table-scroll"><table class="stock-table">
    <thead><tr><th>股票</th><th>现价</th><th>涨跌幅</th><th>换手</th><th>量比</th><th>振幅</th>${showWatch ? '<th>⭐</th>' : ''}</tr></thead>
    <tbody>${tableRows}</tbody>
  </table></div>`;
}

// ─── Abnormal ──────────────────────────────────────────────
async function fetchAbnormal() {
  try {
    const res = await fetch('/abnormal');
    const data = await res.json();
    renderAbnormal(data);
  } catch (e) {
    document.getElementById('market-abnormal').innerHTML = `<div class="error-msg">异动数据加载失败: ${esc(e.message)}</div>`;
  }
}

function renderAbnormal(data) {
  const container = document.getElementById('market-abnormal');
  if (!container) return;

  // Backend returns: {vol_ratio: [...], amplitude: [...], turnover: [...]}
  const volRatio = data.vol_ratio || [];
  const amplitude = data.amplitude || [];
  const turnover = data.turnover || [];

  container.innerHTML = `
    <div class="market-summary-bar">
      <span>📊 放量 <b style="color:#ff9f43">${volRatio.length}</b> 只</span>
      <span>📉 异动 <b style="color:#ff6b6b">${amplitude.length}</b> 只</span>
      <span>🔄 换手 <b style="color:#6c63ff">${turnover.length}</b> 只</span>
      <span style="color:var(--text-muted);font-size:11px" title="量比≥1.5 | 振幅≥8% | 换手≥12%">ⓘ 筛选条件</span>
    </div>
    <div class="abnormal-grid">
      <div class="abnormal-col">
        <h4 class="abnormal-title">📊 量比高于均值 <span style="color:var(--text-muted);font-size:11px">≥1.5</span></h4>
        ${_buildAbnormalTable(volRatio, 'vol_ratio', '量比')}
      </div>
      <div class="abnormal-col">
        <h4 class="abnormal-title">📉 日内振幅异常 <span style="color:var(--text-muted);font-size:11px">≥8%</span></h4>
        ${_buildAbnormalTable(amplitude, 'amplitude', '振幅')}
      </div>
      <div class="abnormal-col">
        <h4 class="abnormal-title">🔄 换手率活跃 <span style="color:var(--text-muted);font-size:11px">≥12%</span></h4>
        ${_buildAbnormalTable(turnover, 'turnover', '换手')}
      </div>
    </div>`;
}

function _buildAbnormalTable(rows, valueKey, label) {
  if (!rows || !rows.length) return '<div class="empty-data">暂无数据</div>';

  // Define thresholds and colors for each metric
  const thresholds = {
    vol_ratio: { levels: [2, 3, 5], colors: ['#aaa', '#ff9f43', '#ff6b3d', '#ff3333'] },
    amplitude: { levels: [10, 15, 20], colors: ['#aaa', '#ff9f43', '#ff6b3d', '#ff3333'] },
    turnover: { levels: [15, 25, 40], colors: ['#aaa', '#6c63ff', '#8b5cf6', '#a78bfa'] }
  };

  const rowsHtml = rows.map(r => {
    const name = r.name || '';
    const code = r.code || '';
    const price = r.price || '--';
    const chg = typeof r.change === 'number' ? r.change : parseFloat(r.change_str || 0);
    const chgCls = chg >= 0 ? 'up' : 'down';
    const val = valueKey ? parseFloat(r[valueKey]) || 0 : 0;

    // Color-code the value based on thresholds
    const cfg = thresholds[valueKey] || { levels: [], colors: ['#aaa', '#aaa'] };
    let valColor = cfg.colors[0];
    for (let i = cfg.levels.length - 1; i >= 0; i--) {
      if (val >= cfg.levels[i]) { valColor = cfg.colors[i + 1]; break; }
    }

    let valDisplay = val.toFixed(2);
    if (valueKey === 'amplitude' || valueKey === 'turnover') valDisplay += '%';

    return `<tr>
      <td><b>${esc(name)}</b><br><span class="stock-code">${esc(code)}</span></td>
      <td>${esc(price)}</td>
      <td class="${chgCls}">${r.change_str || (chg >= 0 ? '+' : '') + chg.toFixed(2) + '%'}</td>
      <td style="color:${valColor};font-weight:bold">${valDisplay}</td>
      <td><button class="watch-btn ${isWatched(code) ? 'watched' : ''}" data-code="${esc(code)}" data-name="${esc(name)}" data-price="${esc(price)}" data-change="${esc(r.change_str || '')}">${isWatched(code) ? '★' : '☆'}</button></td>
    </tr>`;
  }).join('');

  return `<div class="table-scroll"><table class="stock-table mini-table">
    <thead><tr><th>股票</th><th>现价</th><th>涨跌</th><th>${label}</th><th>自选</th></tr></thead>
    <tbody>${rowsHtml}</tbody>
  </table></div>`;
}

// ─── Watchlist ─────────────────────────────────────────────
function getWatchlist() {
  try {
    return JSON.parse(localStorage.getItem('kb_watchlist') || '[]');
  } catch { return []; }
}

function saveWatchlist(list) {
  try { localStorage.setItem('kb_watchlist', JSON.stringify(list)); } catch {}
}

function isWatched(code) {
  return getWatchlist().some(w => w.code === code);
}

function toggleWatch(code, name, price, change) {
  let list = getWatchlist();
  const idx = list.findIndex(w => w.code === code);
  if (idx >= 0) {
    list.splice(idx, 1);
  } else {
    list.push({ code, name, price: price || '', change: change || '', added: Date.now() });
  }
  saveWatchlist(list);
  renderWatchlist();
  // Update all watch buttons
  document.querySelectorAll(`.watch-btn[data-code="${CSS.escape(code)}"]`).forEach(btn => {
    const isNowWatched = idx < 0;
    btn.textContent = isNowWatched ? '★' : '☆';
    btn.classList.toggle('watched', isNowWatched);
  });
}

function removeFromWatch(code) {
  let list = getWatchlist();
  list = list.filter(w => w.code !== code);
  saveWatchlist(list);
  renderWatchlist();
}

function renderWatchlist() {
  const container = document.getElementById('watchlist');
  if (!container) return;
  const list = getWatchlist();
  if (!list.length) {
    container.innerHTML = '<div class="empty-data">暂无自选股</div>';
    return;
  }
  container.innerHTML = list.map(w => `
    <div class="watch-item" onclick="q.value='${esc(w.name || w.code)}';doSearch()">
      <span class="watch-name">${esc(w.name || '')}</span>
      <span class="watch-code">${esc(w.code || '')}</span>
      <button class="watch-remove" onclick="event.stopPropagation();removeFromWatch('${esc(w.code)}')">✕</button>
    </div>
  `).join('');
}

// ─── AI Stock Pick ─────────────────────────────────────────
let lastPickQuery = '';

async function doStockPick() {
  const container = document.getElementById('market-pick');
  if (!container) return;

  const queryInput = container.querySelector('.stock-pick-input');
  const userQuery = queryInput ? queryInput.value.trim() : lastPickQuery;

  // Show input on first load
  if (!userQuery && !container.querySelector('.stock-pick-input')) {
    container.innerHTML = `
      <div class="stock-pick-intro">
        <p style="color:var(--text-muted);font-size:14px;margin-bottom:12px">AI 根据实时行情数据，为你精选推荐股票</p>
        <div class="stock-pick-search">
          <input type="text" class="stock-pick-input" placeholder="例：新能源龙头 / AI概念股 / 芯片半导体" style="flex:1;padding:10px 14px;border:1px solid #3a3a5c;border-radius:8px;background:#1a1a2e;color:#eee;font-size:14px" onkeydown="if(event.key==='Enter')doStockPick()">
          <button class="stock-pick-go" onclick="doStockPick()" style="padding:10px 20px;border-radius:8px;border:none;background:linear-gradient(135deg,#6c63ff,#8b5cf6);color:#fff;font-size:14px;cursor:pointer;font-weight:bold">🔍 AI 分析推荐</button>
        </div>
        <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
          ${['新能源','半导体','AI概念','医药','消费'].map(t =>
            `<button class="quick-tag" onclick="document.querySelector('.stock-pick-input').value='${t}龙头企业';doStockPick()" style="padding:4px 12px;border-radius:12px;border:1px solid #3a3a5c;background:transparent;color:#aaa;cursor:pointer;font-size:12px">${t}</button>`
          ).join('')}
        </div>
      </div>`;
    return;
  }

  lastPickQuery = userQuery;
  container.innerHTML = `
    <div class="stock-pick-search">
      <input type="text" class="stock-pick-input" value="${esc(userQuery)}" style="flex:1;padding:10px 14px;border:1px solid #3a3a5c;border-radius:8px;background:#1a1a2e;color:#eee;font-size:14px" onkeydown="if(event.key==='Enter')doStockPick()">
      <button class="stock-pick-go" onclick="doStockPick()" style="padding:10px 20px;border-radius:8px;border:none;background:linear-gradient(135deg,#6c63ff,#8b5cf6);color:#fff;font-size:14px;cursor:pointer;font-weight:bold">🔍 重新分析</button>
    </div>
    <div class="loading-spinner" style="margin-top:24px">🧠 AI 正在分析 <b>${esc(userQuery)}</b> 相关股票…</div>`;

  try {
    const res = await fetch('/stock-pick', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({query: userQuery})
    });
    const data = await res.json();
    renderStockPick(data, container, userQuery);
  } catch (e) {
    container.innerHTML = `
      <div class="stock-pick-search">
        <input type="text" class="stock-pick-input" value="${esc(userQuery)}" style="flex:1;padding:10px 14px;border:1px solid #3a3a5c;border-radius:8px;background:#1a1a2e;color:#eee;font-size:14px">
        <button class="stock-pick-go" onclick="doStockPick()" style="padding:10px 20px;border-radius:8px;border:none;background:linear-gradient(135deg,#6c63ff,#8b5cf6);color:#fff;font-size:14px;cursor:pointer;font-weight:bold">🔍 重试</button>
      </div>
      <div class="error-msg" style="margin-top:12px">荐股失败: ${esc(e.message)}</div>`;
  }
}

function renderStockPick(data, container, userQuery) {
  const picks = data.picks || [];
  const summary = data.summary || data.answer || '';
  const overallConf = data.confidence;

  // Confidence color
  var confColor = '#ff6b6b';
  if (overallConf >= 0.8) confColor = '#00d4aa';
  else if (overallConf >= 0.6) confColor = '#ffd700';
  else if (overallConf >= 0.4) confColor = '#ff9f43';

  // Keep search box at top
  var html =
    '<div class="stock-pick-search" style="margin-bottom:16px">' +
    '  <input type="text" class="stock-pick-input" value="' + esc(userQuery) + '" placeholder="换个方向试试..." style="flex:1;padding:10px 14px;border:1px solid #3a3a5c;border-radius:8px;background:#1a1a2e;color:#eee;font-size:14px" onkeydown="if(event.key===\'Enter\')doStockPick()">' +
    '  <button class="stock-pick-go" onclick="doStockPick()" style="padding:10px 20px;border-radius:8px;border:none;background:linear-gradient(135deg,#6c63ff,#8b5cf6);color:#fff;font-size:14px;cursor:pointer;font-weight:bold">🔍 重新分析</button>' +
    '</div>';

  // Overall confidence bar
  if (overallConf !== undefined) {
    var pct = Math.round(overallConf * 100);
    html += '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;padding:8px 14px;background:linear-gradient(135deg,#1a1a2e,#16213e);border-radius:8px;border:1px solid #2a2a4a">' +
      '<span style="font-size:12px;color:#888">置信度</span>' +
      '<div style="flex:1;height:6px;background:#2a2a4a;border-radius:3px;overflow:hidden">' +
        '<div style="height:100%;width:' + pct + '%;background:' + confColor + ';border-radius:3px;transition:width 0.8s"></div>' +
      '</div>' +
      '<span style="font-weight:bold;font-size:14px;color:' + confColor + '">' + pct + '%</span>' +
    '</div>';
  }

  if (summary) {
    html += '<div class="stock-pick-summary" style="background:linear-gradient(135deg,#1a1a2e,#16213e);border-radius:8px;padding:10px 14px;margin-bottom:14px;border-left:3px solid ' + confColor + ';font-size:13px;color:#ccc;line-height:1.6">📋 ' + esc(summary) + '</div>';
  }

  if (!picks.length) {
    var raw = data.raw_data || [];
    if (raw.length) {
      html += '<div class="stock-pick-grid">';
      raw.forEach(function(r) {
        html += '<div class="index-card" style="flex:1 1 180px;min-width:150px;padding:16px">' +
          '<div class="index-name">' + esc(r.name||'') + ' <span style="color:#888;font-size:11px;display:block">' + esc(r.code||'') + '</span></div>' +
          '<div class="index-price" style="font-size:20px;margin:6px 0">' + esc(r.price||'--') + '</div>' +
          '<div class="index-change" style="font-size:14px;font-weight:bold">' + esc(r.change||'--') + '</div>' +
        '</div>';
      });
      html += '</div>';
    } else {
      html += '<div class="empty-data">暂无推荐结果，请尝试其他选股方向</div>';
    }
    container.innerHTML = html;
    return;
  }

  // New format: analysis object with technical/fundamental/risk
  html += '<div class="stock-pick-grid" style="display:flex;flex-wrap:wrap;gap:12px">';
  picks.forEach(function(p) {
    var name = p.name || '';
    var code = p.code || '';
    var reason = p.reason || '';
    var price = p.price || '--';
    var change = p.change || '--';
    var analysis = p.analysis || {};
    var pickConf = p.confidence;
    var chgNum = parseFloat(change);
    var cls = chgNum >= 0 ? 'up' : 'down';
    var isW = isWatched(code);

    // Pick confidence mini bar
    var confBar = '';
    if (pickConf !== undefined) {
      var pc = Math.round(pickConf * 100);
      var pcColor = pc >= 80 ? '#00d4aa' : pc >= 60 ? '#ffd700' : '#ff9f43';
      confBar = '<div style="display:flex;gap:4px;align-items:center;margin-top:4px">' +
        '<div style="flex:1;height:3px;background:#2a2a4a;border-radius:2px;overflow:hidden">' +
          '<div style="height:100%;width:' + pc + '%;background:' + pcColor + ';border-radius:2px"></div>' +
        '</div>' +
        '<span style="font-size:10px;color:' + pcColor + ';font-weight:bold">' + pc + '%</span>' +
      '</div>';
    }

    // Build analysis lines
    var analysisHtml = '';
    if (analysis.technical || analysis.fundamental || analysis.risk) {
      analysisHtml = '<div style="margin-top:8px;padding-top:8px;border-top:1px solid #2a2a4a;font-size:11px;line-height:1.7">';
      if (analysis.technical) {
        analysisHtml += '<div><span style="color:#6c63ff">📊 技术</span> <span style="color:#bbb">' + esc(analysis.technical) + '</span></div>';
      }
      if (analysis.fundamental) {
        analysisHtml += '<div><span style="color:#00d4aa">💰 基本面</span> <span style="color:#bbb">' + esc(analysis.fundamental) + '</span></div>';
      }
      if (analysis.risk) {
        analysisHtml += '<div><span style="color:#ff9f43">⚠️ 风险</span> <span style="color:#bbb">' + esc(analysis.risk) + '</span></div>';
      }
      analysisHtml += '</div>';
    } else if (reason) {
      // Old format fallback
      analysisHtml = '<div style="color:#ffd700;font-size:12px;margin-top:6px;line-height:1.5">💡 ' + esc(reason) + '</div>';
    }

    html += '<div class="index-card" style="flex:1 1 200px;min-width:180px;padding:16px">' +
      '<div class="index-name">' + esc(name) + ' <span style="color:#888;font-size:11px;display:block">' + esc(code) + '</span></div>' +
      '<div class="index-price" style="font-size:20px;margin:6px 0">' + esc(price) + '</div>' +
      '<div class="index-change ' + cls + '" style="font-size:14px;font-weight:bold">' + esc(change) + '</div>' +
      confBar +
      analysisHtml +
      '<button class="watch-btn ' + (isW ? 'watched' : '') + '" data-code="' + esc(code) + '" data-name="' + esc(name) + '" data-price="' + esc(price) + '" data-change="' + esc(change) + '" style="margin-top:8px;background:none;border:1px solid ' + (isW ? '#ffd700' : '#555') + ';border-radius:6px;cursor:pointer;font-size:12px;padding:4px 10px;color:' + (isW ? '#ffd700' : '#888') + '">' + (isW ? '⭐ 已自选' : '☆ 加自选') + '</button>' +
    '</div>';
  });
  html += '</div>';

  container.innerHTML = html;
}

// ─── Dark Mode ─────────────────────────────────────────────
function toggleDarkMode() {
  document.body.classList.toggle('light-mode');
  const isLight = document.body.classList.contains('light-mode');
  localStorage.setItem('kb_dark_mode', isLight ? 'light' : 'dark');
  const btn = document.getElementById('darkModeBtn');
  if (btn) btn.textContent = isLight ? '🌙 深色' : '☀️ 浅色';
}

function applyDarkModePreference() {
  const saved = localStorage.getItem('kb_dark_mode');
  if (saved === 'light') {
    document.body.classList.add('light-mode');
    const btn = document.getElementById('darkModeBtn');
    if (btn) btn.textContent = '🌙 深色';
  }
}

// ─── Keyboard Shortcuts ────────────────────────────────────
document.addEventListener('keydown', function(e) {
  // Ctrl/Cmd+K: focus search
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    q.focus();
    q.select();
  }
  // Escape: clear search / cancel
  if (e.key === 'Escape') {
    if (document.activeElement === q) {
      if (q.value) {
        q.value = '';
      } else {
        q.blur();
      }
    }
    if (isSearching && currentAbortController) {
      currentAbortController.abort();
    }
  }
});

// ─── Graph Search Input ────────────────────────────────────
// NOTE: Setup moved into init() below since script loads at end of body

// ─── Initialization ────────────────────────────────────────
(function init() {
  applyDarkModePreference();
  getConversations();
  renderHistory();
  renderWatchlist();

  // Graph search input
  const graphSearchInput = document.getElementById('graphSearch');
  if (graphSearchInput) {
    let debounceTimer;
    graphSearchInput.addEventListener('input', function() {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => filterGraph(this.value), 300);
    });
  }

  const graphExportBtn = document.getElementById('graphExportBtn');
  if (graphExportBtn) {
    graphExportBtn.addEventListener('click', exportGraphImage);
  }

  const darkModeBtn = document.getElementById('darkModeBtn');
  if (darkModeBtn) {
    darkModeBtn.addEventListener('click', toggleDarkMode);
  }

  const historyClearBtn = document.getElementById('historyClearBtn');
  if (historyClearBtn) {
    historyClearBtn.addEventListener('click', clearHistory);
  }

  // Cancel search button
  if (cancelBtn) {
    cancelBtn.addEventListener('click', function() {
      if (currentAbortController) {
        currentAbortController.abort();
      }
      isSearching = false;
      cancelBtn.style.display = 'none';
      hideSkeleton();
    });
  }

  // Initial data load
  fetchMarket();

  // Tab switching via event delegation
  document.addEventListener('click', function(e) {
    const tab = e.target.closest('.market-tab');
    if (tab && tab.dataset.tab) {
      switchMarketTab(tab.dataset.tab);
    }
  });

  // Pull-to-refresh on mobile for market
  let touchStartY = 0;
  let touchDeltaY = 0;
  const marketPanels = document.querySelector('.market-panels');
  if (marketPanels) {
    marketPanels.addEventListener('touchstart', function(e) {
      if (this.scrollTop <= 0) {
        touchStartY = e.touches[0].clientY;
      }
    }, { passive: true });

    marketPanels.addEventListener('touchmove', function(e) {
      if (this.scrollTop <= 0) {
        touchDeltaY = e.touches[0].clientY - touchStartY;
      }
    }, { passive: true });

    marketPanels.addEventListener('touchend', function() {
      if (touchDeltaY > 100) {
        if (currentMarketTab === 'limitup') fetchLimitUp();
        else if (currentMarketTab === 'abnormal') fetchAbnormal();
        else if (currentMarketTab === 'pick') doStockPick();
        else fetchMarket();
      }
      touchDeltaY = 0;
    }, { passive: true });
  }

  // Event delegation for watch buttons in dynamic content
  document.addEventListener('click', function(e) {
    const watchBtn = e.target.closest('.watch-btn');
    if (watchBtn && watchBtn.dataset.code) {
      e.stopPropagation();
      toggleWatch(watchBtn.dataset.code, watchBtn.dataset.name, watchBtn.dataset.price, watchBtn.dataset.change);
    }
  });

  // Auto-refresh market every 30 seconds
  setInterval(() => {
    if (document.hidden) return;
    if (currentMarketTab === 'indices' || currentMarketTab === 'sectors') {
      fetchMarket();
    }
  }, 30000);

  // Enter key triggers search
  q.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      doSearch();
    }
  });

  console.log('📚 Knowledge Base UI initialized');

  // ============================================================
  // 🔁 学习引擎 —— 反馈浮层 + 学习中心
  // ============================================================

  // --- State ---
  let currentAnalysis = '';
  let currentImageHash = '';
  let sessionFeedbackCount = 0;
  let feedbackPanelFolded = false;

  function $id(id) { return document.getElementById(id); }

  const fbPanel = $id('feedbackPanel');
  const fbBody = $id('feedbackBody');
  const fbSummary = $id('feedbackSummary');
  const fbText = $id('feedbackText');
  const fbCount = $id('feedbackCount');
  const fbSessionCount = $id('fbSessionCount');
  const fbSaved = $id('feedbackSaved');
  const fbSubmit = $id('feedbackSubmit');
  const fbGood = $id('fbGood');
  const fbBad = $id('fbBad');
  const autoToggleFb = $id('autoApplyToggleFb');
  const autoToggleLearn = $id('autoApplyToggle');

  let fbRating = null;

  function showFeedback(analysis, imageHash) {
    if (!fbSummary || !fbText) return;
    currentAnalysis = analysis || '';
    currentImageHash = imageHash || '';
    fbSummary.textContent = analysis;
    fbText.value = analysis;
    fbRating = null;
    if (fbGood) { fbGood.classList.remove('active-good'); }
    if (fbBad) { fbBad.classList.remove('active-bad'); }
    if (fbSaved) fbSaved.style.display = 'none';
    if (fbSubmit) { fbSubmit.disabled = false; fbSubmit.textContent = '💾 提交反馈'; }
    if (!feedbackPanelFolded && fbBody) fbBody.style.display = '';
  }

  function rateFeedback(rating) {
    fbRating = rating;
    if (rating === 5) {
      if (fbGood) fbGood.classList.add('active-good');
      if (fbBad) fbBad.classList.remove('active-bad');
    } else {
      if (fbBad) fbBad.classList.add('active-bad');
      if (fbGood) fbGood.classList.remove('active-good');
    }
  }

  async function submitFeedback() {
    if (!fbText || !fbSubmit) return;
    var correction = fbText.value.trim();
    if (!correction) { alert('请填写修正内容'); return; }
    if (correction === currentAnalysis) { alert('修正内容与原始分析相同'); return; }
    if (!currentImageHash) { alert('无可用的图片哈希，请先分析图片'); return; }

    fbSubmit.disabled = true;
    fbSubmit.textContent = '提交中...';

    try {
      var r = await fetch('/learn/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: 'vision',
          image_hash: currentImageHash,
          analysis: currentAnalysis,
          correction: correction,
          rating: fbRating
        })
      });
      if (r.ok) {
        if (fbSaved) { fbSaved.style.display = 'block'; setTimeout(function() { fbSaved.style.display = 'none'; }, 2000); }
        sessionFeedbackCount++;
        if (fbSessionCount) fbSessionCount.textContent = sessionFeedbackCount;
        if (fbCount) { fbCount.textContent = sessionFeedbackCount; fbCount.style.display = ''; }
      } else {
        var err = await r.json();
        alert('提交失败: ' + (err.error || '未知错误'));
      }
    } catch (e) {
      alert('网络错误: ' + e.message);
    }
    fbSubmit.disabled = false;
    fbSubmit.textContent = '💾 提交反馈';
  }

  function toggleFeedback() {
    if (!fbBody || !fbPanel) return;
    if (fbBody.style.display === 'none') {
      fbBody.style.display = '';
      feedbackPanelFolded = false;
      fbPanel.classList.remove('folded');
    } else {
      foldFeedback();
    }
  }

  function foldFeedback() {
    if (fbBody) fbBody.style.display = 'none';
    feedbackPanelFolded = true;
    if (fbPanel) fbPanel.classList.add('folded');
  }

  async function onAutoApplyToggle() {
    var checked = autoToggleFb ? autoToggleFb.checked : (autoToggleLearn ? autoToggleLearn.checked : true);
    if (autoToggleFb) autoToggleFb.checked = checked;
    if (autoToggleLearn) autoToggleLearn.checked = checked;
    try {
      await fetch('/learn/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ auto_apply: checked })
      });
    } catch (e) { /* silent */ }
  }

  // --- Learning Center ---
  var learnPage = 1;

  async function loadLearnCenter() {
    try {
      var statsR = await fetch('/learn/stats');
      if (statsR.ok) {
        var stats = await statsR.json();
        var el = $id('statTotal'); if (el) el.textContent = stats.total || 0;
        el = $id('statRated'); if (el) el.textContent = (stats.rated_pct || 0) + '%';
        el = $id('statRecent'); if (el) el.textContent = stats.recent_7d || 0;
        el = $id('statPrefs'); if (el) el.textContent = stats.preferences_count || 0;
      }
    } catch (e) { /* silent */ }

    try {
      var prefsR = await fetch('/learn/preferences');
      if (prefsR.ok) {
        var data = await prefsR.json();
        var prefs = data.preferences || [];
        var container = $id('learnPrefs');
        if (container) {
          if (prefs.length === 0) {
            container.innerHTML = '<div class="learn-empty">暂无偏好规则，提交几次修正后自动提取</div>';
          } else {
            var html = '';
            for (var i = 0; i < prefs.length; i++) {
              var p = prefs[i];
              html += '<div class="learn-pref-item">' +
                '<span class="learn-pref-text">' + esc(p.rule) + '</span>' +
                '<span class="learn-pref-count">x' + p.count + '</span>' +
                '<button class="learn-pref-del" onclick="delPref(\'' + esc(p.rule) + '\')" title="删除">x</button>' +
                '</div>';
            }
            container.innerHTML = html;
          }
        }
      }
    } catch (e) { /* silent */ }

    await loadMemories(1);

    try {
      var setR = await fetch('/learn/settings');
      if (setR.ok) {
        var sd = await setR.json();
        if (autoToggleLearn) autoToggleLearn.checked = sd.auto_apply !== false;
        if (autoToggleFb) autoToggleFb.checked = sd.auto_apply !== false;
      }
    } catch (e) { /* silent */ }
  }

  async function loadMemories(page) {
    learnPage = page;
    try {
      var r = await fetch('/learn/memories?page=' + page + '&page_size=20');
      if (!r.ok) return;
      var data = await r.json();
      var el = $id('memTotal'); if (el) el.textContent = '共 ' + data.total + ' 条';
      var container = $id('learnMemories');
      if (!container) return;
      if (!data.memories || data.memories.length === 0) {
        container.innerHTML = '<div class="learn-empty">暂无记忆记录</div>';
      } else {
        var html = '';
        for (var i = 0; i < data.memories.length; i++) {
          var m = data.memories[i];
          html += '<div class="learn-mem-item">';
          if (m.id) html += '<img class="learn-mem-thumb" src="/learn/media/' + m.id + '" onerror="this.style.display=\'none\'" alt="">';
          html += '<div class="learn-mem-body">' +
            '<div class="learn-mem-analysis">' + esc((m.analysis || '').substring(0, 120)) + '</div>';
          if (m.correction) html += '<div class="learn-mem-correction">' + esc(m.correction.substring(0, 120)) + '</div>';
          html += '<div class="learn-mem-meta">' +
            '<span>' + fmtTime(m.created_at) + '</span>' +
            '<span class="learn-mem-rating">' + (m.rating === 5 ? '👍' : m.rating === 1 ? '👎' : '—') + '</span>' +
            '<span style="font-size:10px;opacity:0.6">' + (m.type || 'vision') + '</span>' +
            '</div></div>';
          html += '<button class="learn-mem-del" onclick="delMem(\'' + m.id + '\')" title="删除">🗑️</button>';
          html += '</div>';
        }
        container.innerHTML = html;
      }
      var totalPages = data.total_pages || 1;
      var pagHtml = '';
      var pag = $id('learnPagination');
      if (pag && totalPages > 1) {
        if (page > 1) pagHtml += '<button class="learn-page-btn" onclick="pg(' + (page-1) + ')">◀ 上页</button>';
        for (var p = 1; p <= totalPages; p++) {
          if (totalPages <= 7 || p === 1 || p === totalPages || Math.abs(p - page) <= 1) {
            pagHtml += '<button class="learn-page-btn' + (p === page ? ' active' : '') + '" onclick="pg(' + p + ')">' + p + '</button>';
          } else if (p === 2 || p === totalPages - 1) {
            pagHtml += '<span style="padding:6px 4px;color:var(--text-muted)">...</span>';
          }
        }
        if (page < totalPages) pagHtml += '<button class="learn-page-btn" onclick="pg(' + (page+1) + '">下页 ▶</button>';
        pag.innerHTML = pagHtml;
      }
    } catch (e) {
      console.error('加载记忆失败:', e);
    }
  }

  async function delMem(memId) {
    if (!confirm('确定删除这条记忆？')) return;
    try { await fetch('/learn/memories/' + memId, { method: 'DELETE' }); } catch (e) {}
    loadMemories(learnPage);
  }

  async function delPref(ruleText) {
    if (!confirm('确定删除偏好规则：' + ruleText + '？')) return;
    try { await fetch('/learn/preferences', { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rule: ruleText }) }); } catch (e) {}
    loadLearnCenter();
  }

  function showLearnTab(ev) {
    if (ev) ev.preventDefault();
    var tabs = document.querySelectorAll('.market-tab');
    for (var i = 0; i < tabs.length; i++) tabs[i].classList.remove('active');
    var learnTab = document.querySelector('[data-tab="learn"]');
    if (learnTab) learnTab.classList.add('active');
    var contents = document.querySelectorAll('.market-tab-content');
    for (var i = 0; i < contents.length; i++) contents[i].style.display = 'none';
    var learnContent = $id('market-learn');
    if (learnContent) { learnContent.style.display = ''; loadLearnCenter(); }
  }

  var tabBtns = document.querySelectorAll('.market-tab');
  for (var i = 0; i < tabBtns.length; i++) {
    tabBtns[i].addEventListener('click', function() {
      if (this.getAttribute('data-tab') === 'learn') loadLearnCenter();
    });
  }

  function esc(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\"/g, '&quot;');
  }

  function fmtTime(iso) {
    if (!iso) return '';
    try { var d = new Date(iso); return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }); }
    catch (e) { return iso.substring(0, 16); }
  }

  // Expose to global scope for onclick
  window.pg = loadMemories;
  window.delMem = delMem;
  window.delPref = delPref;
  window.toggleFeedback = toggleFeedback;
  window.foldFeedback = foldFeedback;
  window.rateFeedback = rateFeedback;
  window.submitFeedback = submitFeedback;
  window.showFeedback = showFeedback;
  window.showLearnTab = showLearnTab;
  window.onAutoApplyToggle = onAutoApplyToggle;

  // Hook vision/video responses → show feedback
  var _origFetch = window.fetch;
  window.fetch = function() {
    var args = arguments;
    return _origFetch.apply(this, args).then(function(resp) {
      try {
        var url = '';
        if (typeof args[0] === 'string') url = args[0];
        else if (args[0] && args[0].url) url = args[0].url;
        if (url.indexOf('/vision') >= 0 || url.indexOf('/video-analysis') >= 0) {
          resp.clone().json().then(function(data) {
            var a = data.answer || data.description || '';
            var h = data.image_hash || '';
            if (a) showFeedback(a, h);
          }).catch(function() {});
        }
      } catch (e) {}
      return resp;
    });
  };
})();
