const DEFAULT_API_BASE_URL = 'https://santoshbadgu-autosolver-agent-api.hf.space';
const API_BASE_STORAGE_KEY = 'autosolver_api_base_url';
const SOLVER_CACHE_VERSION = 'v30-trim-cycle-cache';

const $ = (id) => document.getElementById(id);

const inputText = $('inputText');
const runBtn = $('runBtn');
const cancelBtn = $('cancelBtn');
const clearBtn = $('clearBtn');
const fileInput = $('fileInput');
const pickFileBtn = $('pickFileBtn');
const loadSampleBtn = $('loadSampleBtn');
const dropzone = $('dropzone');
const outputText = $('outputText');
const resultBody = $('resultBody');
const engineStatus = $('engineStatus');
const runtimeStat = $('runtimeStat');
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
const settingsDialog = $('settingsDialog');
const apiBaseInput = $('apiBaseInput');

const MAX_RENDER_ROWS = 200;
const RESULT_CACHE_LIMIT = 8;
const resultCache = new Map();
let apiBaseUrl = getApiBaseUrl();
let currentRows = [];
let currentOutput = '';
let currentFilename = 'autosolver_input.txt';
let progressTimer = null;
let currentProgress = 0;
let controller = null;

function getApiBaseUrl() {
  return (localStorage.getItem(API_BASE_STORAGE_KEY) || DEFAULT_API_BASE_URL).replace(/\/+$/, '');
}

function showToast(message, timeout = 2600) {
  toast.textContent = message;
  toast.classList.add('show');
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove('show'), timeout);
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
  setProgress(progress, label);
}

function startSmoothProgress(limit = 92, step = 1) {
  window.clearInterval(progressTimer);
  progressTimer = window.setInterval(() => {
    if (currentProgress < limit) {
      const nextStep = currentProgress < 35 ? step + 2 : currentProgress < 70 ? step + 1 : step;
      setProgress(currentProgress + nextStep, progressLabel.textContent);
    }
  }, 520);
}

function stopSmoothProgress() {
  window.clearInterval(progressTimer);
  progressTimer = null;
}

async function getInputCacheKey(input) {
  const prefix = `${SOLVER_CACHE_VERSION}:${apiBaseUrl}:`;
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

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

async function warmEngine({ silent = false } = {}) {
  apiBaseUrl = getApiBaseUrl();
  apiBaseInput.value = apiBaseUrl;
  if (apiBaseUrl === DEFAULT_API_BASE_URL) {
    engineStatus.textContent = '待配置 API';
    engineStatus.classList.remove('ok');
    setStage(0, '配置后端地址', 0);
    if (!silent) showToast('请先在 API 设置中填写 Hugging Face Space 地址。', 4200);
    return false;
  }

  engineStatus.textContent = 'Python 引擎预热中';
  engineStatus.classList.remove('ok');
  setStage(0, 'Python 引擎预热中', Math.max(currentProgress, 8));
  try {
    const res = await fetch(`${apiBaseUrl}/api/health`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    engineStatus.textContent = '引擎就绪';
    engineStatus.classList.add('ok');
    setStage(1, '引擎已就绪', 24);
    if (!silent) showToast('求解引擎已就绪。');
    return true;
  } catch (error) {
    engineStatus.textContent = '等待唤醒';
    engineStatus.classList.remove('ok');
    setStage(0, '首次唤醒可能需要几十秒', 12);
    if (!silent) showToast('后端暂未响应，可能正在冷启动。稍后会继续尝试。', 5200);
    return false;
  }
}

async function solveInput() {
  const input = inputText.value.trim();
  if (!input) {
    showToast('请先上传或粘贴赛题 txt 数据。');
    return;
  }
  if (apiBaseUrl === DEFAULT_API_BASE_URL) {
    settingsDialog.showModal();
    showToast('请先填写 Hugging Face Space API 地址。', 4200);
    return;
  }

  const cacheKey = await getInputCacheKey(input);
  const cachedPayload = getCachedResult(cacheKey);
  if (cachedPayload) {
    stopSmoothProgress();
    runBtn.disabled = false;
    cancelBtn.disabled = true;
    setStage(3, '命中本地结果缓存', 100);
    engineStatus.textContent = '缓存命中';
    engineStatus.classList.add('ok');
    renderResult(cachedPayload);
    showToast('命中最近结果缓存，已直接展示。');
    return;
  }

  controller?.abort();
  controller = new AbortController();
  runBtn.disabled = true;
  cancelBtn.disabled = false;
  currentRows = [];
  currentOutput = '';
  runtimeStat.textContent = rowStat.textContent = taskStat.textContent = courierStat.textContent = '--';
  resultBody.innerHTML = '<tr><td colspan="4" class="empty">AutoSolver 正在计算，请稍候...</td></tr>';
  outputText.textContent = '求解中...';
  engineStatus.textContent = '运行中';
  engineStatus.classList.remove('ok');
  setStage(1, '校验输入数据', 28);
  startSmoothProgress();

  const warmed = await warmEngine({ silent: true });
  if (!warmed) {
    setStage(0, '正在唤醒后端服务', 18);
    await wait(3500);
  }

  setStage(2, 'AutoSolver 正在求解', 46);
  try {
    const res = await fetch(`${apiBaseUrl}/api/solve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: currentFilename, input_text: input }),
      signal: controller.signal,
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(payload.detail || `求解请求失败：HTTP ${res.status}`);
    }
    stopSmoothProgress();
    setStage(3, '结果已生成', 100);
    engineStatus.textContent = '求解完成';
    engineStatus.classList.add('ok');
    rememberResult(cacheKey, payload);
    renderResult(payload);
    showToast('求解完成，结果已生成。');
  } catch (error) {
    stopSmoothProgress();
    if (error.name === 'AbortError') return;
    engineStatus.textContent = '求解失败';
    engineStatus.classList.remove('ok');
    setProgress(0, '运行失败');
    resultBody.innerHTML = `<tr><td colspan="4" class="empty">${escapeHtml(error.message || '求解失败')}</td></tr>`;
    outputText.textContent = error.message || '求解失败';
    showToast(error.message || '求解失败，请检查后端地址和输入。', 5200);
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
  runtimeStat.textContent = typeof stats.runtime === 'number' ? `${stats.runtime.toFixed(2)}s` : '--';
  rowStat.textContent = String(stats.rows ?? currentRows.length);
  taskStat.textContent = String(stats.tasks ?? countTasks(currentRows));
  courierStat.textContent = String(stats.couriers ?? countCouriers(currentRows));
  renderTable();
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
  const text = await file.text();
  inputText.value = text;
  updateFileMeta(file.name, text);
  showToast(`已导入 ${file.name}`);
}

function clearAll() {
  controller?.abort();
  cancelBtn.disabled = true;
  inputText.value = '';
  currentRows = [];
  currentOutput = '';
  currentFilename = 'autosolver_input.txt';
  fileBadge.textContent = '等待导入';
  fileBadge.classList.remove('ok');
  fileMeta.innerHTML = '<span>文件：--</span><span>大小：--</span><span>行数：--</span>';
  outputText.textContent = '等待求解...';
  resultBody.innerHTML = '<tr><td colspan="4" class="empty">上传数据后启动求解，结果会显示在这里。</td></tr>';
  runtimeStat.textContent = rowStat.textContent = taskStat.textContent = courierStat.textContent = '--';
  setProgress(0, '待机');
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
  setProgress(0, '已取消');
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

function bindEvents() {
  pickFileBtn.addEventListener('click', () => fileInput.click());
  runBtn.addEventListener('click', solveInput);
  cancelBtn.addEventListener('click', cancelSolve);
  clearBtn.addEventListener('click', clearAll);
  searchInput.addEventListener('input', renderTable);

  inputText.addEventListener('input', () => {
    if (inputText.value.trim()) updateFileMeta('', inputText.value);
  });

  loadSampleBtn.addEventListener('click', async () => {
    try {
      const res = await fetch('sample/large_seed301.txt', { cache: 'no-store' });
      const text = await res.text();
      inputText.value = text;
      updateFileMeta('large_seed301.txt', text);
      showToast('示例数据已载入。');
    } catch {
      showToast('示例数据加载失败。');
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

  $('copyInputBtn').addEventListener('click', async () => {
    await navigator.clipboard.writeText(inputText.value || '');
    showToast('输入已复制。');
  });
  $('copyResultBtn').addEventListener('click', async () => {
    if (!currentOutput) return showToast('暂无可复制结果。');
    await navigator.clipboard.writeText(currentOutput);
    showToast('结果 TXT 已复制。');
  });
  $('downloadTxtBtn').addEventListener('click', () => {
    if (!currentOutput) return showToast('暂无可下载结果。');
    download(`autosolver_result_${Date.now()}.txt`, currentOutput);
  });
  $('downloadJsonBtn').addEventListener('click', () => {
    if (!currentRows.length) return showToast('暂无可下载结果。');
    download(`autosolver_result_${Date.now()}.json`, JSON.stringify(currentRows, null, 2), 'application/json;charset=utf-8');
  });

  $('settingsBtn').addEventListener('click', () => {
    apiBaseInput.value = getApiBaseUrl();
    settingsDialog.showModal();
  });
  $('saveApiBtn').addEventListener('click', () => {
    const value = apiBaseInput.value.trim().replace(/\/+$/, '');
    if (!value || !/^https?:\/\//.test(value)) {
      showToast('请输入完整的 http 或 https 地址。');
      return;
    }
    localStorage.setItem(API_BASE_STORAGE_KEY, value);
    apiBaseUrl = value;
    settingsDialog.close();
    warmEngine();
  });
  $('resetApiBtn').addEventListener('click', () => {
    localStorage.removeItem(API_BASE_STORAGE_KEY);
    apiBaseUrl = DEFAULT_API_BASE_URL;
    apiBaseInput.value = apiBaseUrl;
    warmEngine();
  });
}

bindEvents();
setProgress(0, '唤醒引擎');
warmEngine({ silent: true });
