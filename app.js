const UI_PERF_VERSION = 'v7-no-flicker-smooth-scroll';
const API_BASE_URL = 'https://santoshbadgu-autosolver-agent-api.hf.space';
const SOLVER_CACHE_VERSION = 'v30-trim-cycle-cache';
const MAX_RENDER_ROWS = 200;
const RESULT_CACHE_LIMIT = 8;
const HISTORY_LIMIT = 8;
const SAMPLE_PATH = 'sample/large_seed301.txt';
const RAW_SAMPLE_URL = 'https://raw.githubusercontent.com/cpu-broke/autosolver-agent-web/main/sample/large_seed301.txt';

const $ = (id) => document.getElementById(id);

const inputText = $('inputText');
const runBtn = $('runBtn');
const cancelBtn = $('cancelBtn');
const clearBtn = $('clearBtn');
const fileInput = $('fileInput');
const pickFileBtn = $('pickFileBtn');
const loadSampleBtn = $('loadSampleBtn');
const heroImportAction = $('heroImportAction');
const heroSolveAction = $('heroSolveAction');
const heroResultAction = $('heroResultAction');
const dropzone = $('dropzone');
const outputText = $('outputText');
const resultBody = $('resultBody');
const engineStatus = $('engineStatus');
const runBadge = $('runBadge');
const runtimeStat = $('runtimeStat');
const algoRuntimeStat = $('algoRuntimeStat');
const rowStat = $('rowStat');
const taskStat = $('taskStat');
const courierStat = $('courierStat');
const progressNumber = $('progressNumber');
const progressLabel = $('progressLabel');
const ringBar = $('ringBar');
const toast = $('toast');
const fileBadge = $('fileBadge');
const fileMeta = $('fileMeta');
const searchInput = $('searchInput');
const resultPanel = $('resultPanel');
const mascotWidget = $('mascotWidget');
const mascotText = $('mascotText');
const historyList = $('historyList');
const clearHistoryBtn = $('clearHistoryBtn');
const cartoonStage = $('cartoonStage');

const resultCache = new Map();
let historyItems = [];
let currentRows = [];
let currentOutput = '';
let currentFilename = 'autosolver_input.txt';
let progressTimer = null;
let currentProgress = 0;
let controller = null;
let mascotMode = 'idle';
let prewarmStarted = false;

function showToast(message, timeout = 2600) {
  toast.textContent = message;
  toast.classList.add('show');
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove('show'), timeout);
}

function setMascot(mode, text) {
  mascotMode = mode;
  mascotWidget.classList.remove('is-idle', 'is-solving', 'is-done', 'is-tap');
  mascotWidget.classList.add(`is-${mode}`);
  mascotText.textContent = text;
}

function nudgeMascot(nextMode = mascotMode) {
  mascotWidget.classList.remove('is-tap');
  void mascotWidget.offsetWidth;
  mascotWidget.classList.add('is-tap');
  window.setTimeout(() => mascotWidget.classList.remove('is-tap'), 520);
  if (mascotMode === 'done' && nextMode !== 'done') {
    setMascot('idle', '摸鱼中');
  }
}

function resetStages() {
  document.querySelectorAll('.stage-list li').forEach((li) => li.classList.remove('active', 'done'));
  runBadge.textContent = '待机';
  runBadge.classList.remove('ok');
  runBadge.classList.add('warning');
}

function setProgress(value, label = '') {
  currentProgress = Math.max(0, Math.min(100, Math.round(value)));
  progressNumber.textContent = `${currentProgress}%`;
  if (label) progressLabel.textContent = label;
  const circumference = 326.72;
  ringBar.style.strokeDashoffset = String(circumference * (1 - currentProgress / 100));
}

function setStage(stageIndex, label, progress) {
  document.querySelectorAll('.stage-list li').forEach((li, idx) => {
    li.classList.toggle('active', idx === stageIndex);
    li.classList.toggle('done', idx < stageIndex);
  });
  runBadge.textContent = label;
  setProgress(progress, label);
}

function startSmoothProgress(limit = 92) {
  window.clearInterval(progressTimer);
  progressTimer = window.setInterval(() => {
    if (currentProgress < limit) {
      const drift = currentProgress < 35 ? 3 : currentProgress < 70 ? 2 : 1;
      setProgress(currentProgress + drift, progressLabel.textContent);
    }
  }, 620);
}

function stopSmoothProgress() {
  window.clearInterval(progressTimer);
  progressTimer = null;
}

async function getInputCacheKey(input) {
  const prefix = `${SOLVER_CACHE_VERSION}:${API_BASE_URL}:`;
  if (window.crypto?.subtle && window.TextEncoder) {
    const bytes = new TextEncoder().encode(input);
    const digest = await window.crypto.subtle.digest('SHA-256', bytes);
    const hash = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
    return prefix + hash;
  }
  return prefix + input;
}

function clonePayload(payload) {
  return typeof structuredClone === 'function'
    ? structuredClone(payload)
    : JSON.parse(JSON.stringify(payload));
}

function getCachedResult(key) {
  if (!resultCache.has(key)) return null;
  const payload = resultCache.get(key);
  resultCache.delete(key);
  resultCache.set(key, payload);
  return clonePayload(payload);
}

function rememberResult(key, payload) {
  resultCache.set(key, clonePayload(payload));
  while (resultCache.size > RESULT_CACHE_LIMIT) {
    resultCache.delete(resultCache.keys().next().value);
  }
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function updateFileMeta(filename, text) {
  const bytes = new Blob([text]).size;
  const lines = text ? text.split(/\r\n|\r|\n/).filter(Boolean).length : 0;
  currentFilename = filename || 'autosolver_input.txt';
  fileBadge.textContent = filename ? '已导入' : '手动输入';
  fileBadge.classList.add('ok');
  fileMeta.innerHTML = `
    <span>文件：${escapeHtml(filename || '粘贴输入')}</span>
    <span>大小：${formatBytes(bytes)}</span>
    <span>行数：${lines.toLocaleString('zh-CN')}</span>
  `;
}

function getSampleUrls() {
  const repoName = window.location.pathname.split('/').filter(Boolean)[0];
  return [
    new URL(SAMPLE_PATH, window.location.href).href,
    repoName ? `/${repoName}/${SAMPLE_PATH}` : `/${SAMPLE_PATH}`,
    RAW_SAMPLE_URL,
  ];
}

async function loadCompleteSample() {
  let lastError = null;
  for (const url of getSampleUrls()) {
    try {
      const res = await fetch(url, { cache: 'force-cache' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const text = await res.text();
      if (text.length < 100000) throw new Error('示例数据不完整');
      return text;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error('示例加载失败');
}

async function warmEngine({ silent = false, reflectProgress = false } = {}) {
  engineStatus.textContent = '引擎预热中';
  engineStatus.classList.remove('ok');
  if (reflectProgress) setStage(0, '唤醒', Math.max(currentProgress, 8));
  try {
    const res = await fetch(`${API_BASE_URL}/api/health`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    engineStatus.textContent = '引擎就绪';
    engineStatus.classList.add('ok');
    if (reflectProgress) setProgress(Math.max(currentProgress, 12), progressLabel.textContent);
    if (!silent) showToast('求解引擎已就绪。');
    return true;
  } catch {
    engineStatus.textContent = '正在唤醒求解引擎';
    engineStatus.classList.remove('ok');
    if (reflectProgress) setStage(0, '唤醒中', 12);
    if (!silent) showToast('后端服务正在唤醒，首次可能需要几十秒。', 4200);
    return false;
  }
}

async function solveInput() {
  nudgeMascot();
  const input = inputText.value.trim();
  if (!input) {
    showToast('请先导入、载入示例或粘贴待选数据。');
    setMascot('idle', '摸鱼中');
    return;
  }

  setMascot('solving', '求解中');
  const solveTotalStart = performance.now();
  const cacheKey = await getInputCacheKey(input);
  const cachedPayload = getCachedResult(cacheKey);
  if (cachedPayload) {
    stopSmoothProgress();
    setStage(3, '生成结果', 100);
    cachedPayload.stats = { ...(cachedPayload.stats || {}), total_runtime: 0 };
    renderResult(cachedPayload);
    addHistoryItem(cachedPayload, true);
    setMascot('done', '求解完毕');
    resultPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    showToast('命中最近结果缓存，已直接展示。');
    return;
  }

  controller?.abort();
  controller = new AbortController();
  runBtn.disabled = true;
  cancelBtn.disabled = false;
  currentRows = [];
  currentOutput = '';
  runtimeStat.textContent = algoRuntimeStat.textContent = rowStat.textContent = taskStat.textContent = courierStat.textContent = '--';
  resultBody.innerHTML = '<tr><td colspan="4" class="empty">AutoSolver 正在计算，请稍候...</td></tr>';
  outputText.textContent = '求解中...';
  engineStatus.textContent = '运行中';
  engineStatus.classList.remove('ok');
  setStage(1, '读取数据', 30);
  startSmoothProgress();

  const warmed = await warmEngine({ silent: true, reflectProgress: true });
  if (!warmed) {
    setStage(0, '唤醒中', 18);
    await wait(3000);
  }

  setStage(2, '执行算法', 48);
  try {
    const res = await fetch(`${API_BASE_URL}/api/solve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: currentFilename, input_text: input }),
      signal: controller.signal,
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(payload.detail || `求解请求失败：HTTP ${res.status}`);
    stopSmoothProgress();
    setStage(3, '生成结果', 100);
    engineStatus.textContent = '完成';
    engineStatus.classList.add('ok');
    payload.stats = { ...(payload.stats || {}), total_runtime: (performance.now() - solveTotalStart) / 1000 };
    rememberResult(cacheKey, payload);
    renderResult(payload);
    addHistoryItem(payload, false);
    setMascot('done', '求解完毕');
    resultPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    showToast('求解完成。');
  } catch (error) {
    stopSmoothProgress();
    if (error.name === 'AbortError') return;
    engineStatus.textContent = '失败';
    engineStatus.classList.remove('ok');
    setProgress(0, '失败');
    setMascot('idle', '摸鱼中');
    resultBody.innerHTML = `<tr><td colspan="4" class="empty">${escapeHtml(error.message || '求解失败')}</td></tr>`;
    outputText.textContent = error.message || '求解失败';
    showToast(error.message || '求解失败，请检查输入。', 5200);
  } finally {
    runBtn.disabled = false;
    cancelBtn.disabled = true;
  }
}

function renderResult(payload) {
  currentRows = payload.rows || [];
  currentOutput = payload.output_text || rowsToText(currentRows);
  outputText.textContent = currentOutput || '无输出';
  const stats = payload.stats || {};
  const shownRuntime = typeof stats.total_runtime === 'number' ? stats.total_runtime : (typeof stats.runtime === 'number' ? stats.runtime : payload.runtime);
  const algoRuntime = typeof stats.runtime === 'number' ? stats.runtime : (typeof payload.runtime === 'number' ? payload.runtime : null);
  runtimeStat.textContent = typeof shownRuntime === 'number' ? `${shownRuntime.toFixed(2)}s` : '--';
  algoRuntimeStat.textContent = typeof algoRuntime === 'number' ? `${algoRuntime.toFixed(2)}s` : '--';
  rowStat.textContent = String(stats.rows ?? currentRows.length);
  taskStat.textContent = String(stats.tasks ?? countTasks(currentRows));
  courierStat.textContent = String(stats.couriers ?? countCouriers(currentRows));
  renderTable();
}

function addHistoryItem(payload, cached) {
  const stats = payload.stats || {};
  const item = {
    id: Date.now(),
    time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    filename: currentFilename,
    rows: stats.rows ?? (payload.rows || []).length,
    runtime: cached ? '缓存' : (typeof stats.total_runtime === 'number' ? `${stats.total_runtime.toFixed(2)}s` : (typeof stats.runtime === 'number' ? `${stats.runtime.toFixed(2)}s` : '--')),
    cached,
    payload: clonePayload(payload),
  };
  historyItems.unshift(item);
  historyItems = historyItems.slice(0, HISTORY_LIMIT);
  renderHistory();
}

function renderHistory() {
  historyList.innerHTML = '';
  if (!historyItems.length) {
    historyList.innerHTML = '<p class="history-empty">暂无历史记录</p>';
    return;
  }
  const frag = document.createDocumentFragment();
  historyItems.forEach((item, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'history-item';
    button.innerHTML = `
      <strong>${index + 1}. ${escapeHtml(item.filename)}</strong>
      <span>${item.time} · ${item.rows} 行 · ${item.runtime}${item.cached ? ' · 缓存' : ''}</span>
    `;
    button.addEventListener('click', () => {
      nudgeMascot();
      renderResult(item.payload);
      resultPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
      showToast('已恢复历史结果。');
    });
    frag.appendChild(button);
  });
  historyList.appendChild(frag);
}

function renderTable() {
  const query = searchInput.value.trim().toLowerCase();
  const rows = query
    ? currentRows.filter((row) => `${row.task} ${(row.couriers || []).join(',')}`.toLowerCase().includes(query))
    : currentRows;
  const visibleRows = rows.slice(0, MAX_RENDER_ROWS);

  resultBody.innerHTML = '';
  if (!rows.length) {
    resultBody.innerHTML = `<tr><td colspan="4" class="empty">${currentRows.length ? '没有匹配结果。' : '暂无结果。'}</td></tr>`;
    return;
  }

  const frag = document.createDocumentFragment();
  visibleRows.forEach((row, idx) => {
    const couriers = row.couriers || [];
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${idx + 1}</td>
      <td>${escapeHtml(row.task)}</td>
      <td>${escapeHtml(couriers.join(', '))}</td>
      <td>${couriers.length}</td>
    `;
    frag.appendChild(tr);
  });
  if (rows.length > MAX_RENDER_ROWS) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td colspan="4" class="empty">已显示前 ${MAX_RENDER_ROWS} 行，共 ${rows.length} 行；复制和下载仍包含完整结果。</td>`;
    frag.appendChild(tr);
  }
  resultBody.appendChild(frag);
}

function rowsToText(rows) {
  return rows.map((row) => `${row.task}\t${(row.couriers || []).join(',')}`).join('\n');
}

function countTasks(rows) {
  const set = new Set();
  rows.forEach((row) => String(row.task || '').split(',').forEach((task) => task.trim() && set.add(task.trim())));
  return set.size;
}

function countCouriers(rows) {
  const set = new Set();
  rows.forEach((row) => (row.couriers || []).forEach((courier) => courier && set.add(courier)));
  return set.size;
}

function download(filename, content, type = 'text/plain;charset=utf-8') {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function readFile(file) {
  nudgeMascot();
  const text = await file.text();
  inputText.value = text;
  updateFileMeta(file.name, text);
  inputText.scrollTop = 0;
  showToast(`已导入 ${file.name}`);
}

function clearAll() {
  nudgeMascot();
  controller?.abort();
  controller = null;
  stopSmoothProgress();
  runBtn.disabled = false;
  cancelBtn.disabled = true;
  inputText.value = '';
  currentRows = [];
  currentOutput = '';
  currentFilename = 'autosolver_input.txt';
  fileBadge.textContent = '等待导入';
  fileBadge.classList.remove('ok');
  fileMeta.innerHTML = '<span>文件：-</span><span>大小：-</span><span>行数：-</span>';
  outputText.textContent = '等待求解...';
  resultBody.innerHTML = '<tr><td colspan="4" class="empty">导入数据后启动求解，结果会显示在这里。</td></tr>';
  runtimeStat.textContent = algoRuntimeStat.textContent = rowStat.textContent = taskStat.textContent = courierStat.textContent = '--';
  resetStages();
  setProgress(0, '待机');
  setMascot('idle', '摸鱼中');
}

function cancelSolve() {
  if (!controller) return;
  controller.abort();
  controller = null;
  stopSmoothProgress();
  runBtn.disabled = false;
  cancelBtn.disabled = true;
  engineStatus.textContent = '已取消';
  engineStatus.classList.remove('ok');
  resetStages();
  setProgress(0, '已取消');
  setMascot('idle', '摸鱼中');
  showToast('已取消本次求解。');
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (ch) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    "'": '&#39;',
    '"': '&quot;',
  }[ch]));
}

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}


function setupStageMotion() {
  if (!cartoonStage) return;
  cartoonStage.addEventListener('pointermove', (event) => {
    const rect = cartoonStage.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width - 0.5) * 2;
    const y = ((event.clientY - rect.top) / rect.height - 0.5) * 2;
    cartoonStage.style.setProperty('--mx', x.toFixed(3));
    cartoonStage.style.setProperty('--my', y.toFixed(3));
  });
  cartoonStage.addEventListener('pointerleave', () => {
    cartoonStage.style.setProperty('--mx', '0');
    cartoonStage.style.setProperty('--my', '0');
  });
}


function prewarmBackend() {
  if (prewarmStarted) return;
  prewarmStarted = true;
  const run = async (attempt = 0) => {
    const ok = await warmEngine({ silent: true, reflectProgress: false });
    if (!ok && attempt < 2) {
      window.setTimeout(() => run(attempt + 1), attempt === 0 ? 3500 : 8000);
    }
  };
  run();
}

function bindEvents() {
  pickFileBtn.addEventListener('click', () => {
    nudgeMascot();
    fileInput.click();
  });
  heroImportAction.addEventListener('click', () => {
    nudgeMascot();
    fileInput.click();
  });
  heroSolveAction.addEventListener('click', solveInput);
  heroResultAction.addEventListener('click', () => {
    nudgeMascot();
    resultPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  mascotWidget.addEventListener('click', () => {
    if (mascotMode === 'done') setMascot('idle', '摸鱼中');
    nudgeMascot();
  });
  runBtn.addEventListener('click', solveInput);
  cancelBtn.addEventListener('click', cancelSolve);
  clearBtn.addEventListener('click', clearAll);
  clearHistoryBtn.addEventListener('click', () => {
    nudgeMascot();
    historyItems = [];
    renderHistory();
  });
  searchInput.addEventListener('input', renderTable);

  inputText.addEventListener('input', () => {
    if (mascotMode === 'done') setMascot('idle', '摸鱼中');
    if (inputText.value.trim()) updateFileMeta('', inputText.value);
  });

  loadSampleBtn.addEventListener('click', async () => {
    nudgeMascot();
    loadSampleBtn.disabled = true;
    loadSampleBtn.textContent = '正在载入';
    try {
      const text = await loadCompleteSample();
      inputText.value = text;
      inputText.scrollTop = 0;
      updateFileMeta('large_seed301.txt', text);
      showToast('完整 301 示例已载入。');
    } catch (error) {
      showToast(`${error.message || '示例加载失败'}，请确认 sample/large_seed301.txt 已上传。`, 5200);
    } finally {
      loadSampleBtn.disabled = false;
      loadSampleBtn.textContent = '载入示例';
    }
  });

  fileInput.addEventListener('change', (event) => {
    const file = event.target.files && event.target.files[0];
    if (file) readFile(file);
  });

  ['dragenter', 'dragover'].forEach((name) => dropzone.addEventListener(name, (event) => {
    event.preventDefault();
    dropzone.classList.add('dragover');
  }));
  ['dragleave', 'drop'].forEach((name) => dropzone.addEventListener(name, (event) => {
    event.preventDefault();
    dropzone.classList.remove('dragover');
  }));
  dropzone.addEventListener('drop', (event) => {
    const file = event.dataTransfer.files && event.dataTransfer.files[0];
    if (file) readFile(file);
  });

  $('copyResultBtn').addEventListener('click', async () => {
    nudgeMascot();
    if (!currentOutput) return showToast('暂无可复制结果。');
    await navigator.clipboard.writeText(currentOutput);
    showToast('结果 TXT 已复制。');
  });
  $('downloadTxtBtn').addEventListener('click', () => {
    nudgeMascot();
    if (!currentOutput) return showToast('暂无可下载结果。');
    download(`hackathon_result_${Date.now()}.txt`, currentOutput);
  });
  $('downloadJsonBtn').addEventListener('click', () => {
    nudgeMascot();
    if (!currentRows.length) return showToast('暂无可下载结果。');
    download(`hackathon_result_${Date.now()}.json`, JSON.stringify(currentRows, null, 2), 'application/json;charset=utf-8');
  });
}

setupStageMotion();
bindEvents();
renderHistory();
resetStages();
setProgress(0, '待机');
setMascot('idle', '摸鱼中');
prewarmBackend();
window.addEventListener('focus', () => {
  if (!engineStatus.classList.contains('ok')) warmEngine({ silent: true });
});
