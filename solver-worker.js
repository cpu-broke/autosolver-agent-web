let pyodide = null;
let solverReady = false;
let initPromise = null;

const RESULT_CACHE_LIMIT = 8;
const resultCache = new Map();

function postStatus(stage, label, progress) {
  self.postMessage({ type: 'status', stage, label, progress });
}

function getCacheKey(input) {
  return input || '';
}

function rememberResult(key, payload) {
  resultCache.set(key, payload);
  while (resultCache.size > RESULT_CACHE_LIMIT) {
    resultCache.delete(resultCache.keys().next().value);
  }
}

function getCachedResult(key) {
  if (!resultCache.has(key)) return null;
  const payload = resultCache.get(key);
  resultCache.delete(key);
  resultCache.set(key, payload);
  return payload;
}

async function ensureSolver() {
  if (solverReady) return;
  if (initPromise) return initPromise;
  initPromise = (async () => {
    postStatus(0, 'Python 引擎预热中', 8);
    importScripts('https://cdn.jsdelivr.net/pyodide/v0.27.5/full/pyodide.js');
    pyodide = await loadPyodide({ indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.27.5/full/' });

    postStatus(1, '加载内置 solver.py', 24);
    const response = await fetch('./solver.py?v=v30-trim-cycle-cache', { cache: 'force-cache' });
    if (!response.ok) throw new Error('solver.py 加载失败：' + response.status);
    const solverCode = await response.text();
    pyodide.runPython(solverCode);
    pyodide.runPython(`
import json, time

def solve_to_json(input_text):
    t0 = time.time()
    ans = solve(input_text)
    rows = []
    for item in ans:
        try:
            task = item[0]
            couriers = list(item[1])
        except Exception:
            continue
        rows.append({'task': task, 'couriers': couriers})
    return json.dumps({'rows': rows, 'runtime': time.time() - t0}, ensure_ascii=False)
`);
    solverReady = true;
    postStatus(1, '算法加载完成', 35);
  })();
  return initPromise;
}

self.onmessage = async (event) => {
  const { id, input, type } = event.data || {};
  try {
    await ensureSolver();
    if (type === 'warmup') {
      self.postMessage({ type: 'ready', id });
      return;
    }

    const cacheKey = getCacheKey(input);
    const cachedPayload = getCachedResult(cacheKey);
    if (cachedPayload) {
      self.postMessage({ type: 'result', id, payload: cachedPayload, cached: true });
      return;
    }

    postStatus(2, '解析输入数据', 46);
    pyodide.globals.set('WEB_INPUT_TEXT', input || '');
    postStatus(3, 'AutoSolver 正在自主求解', 68);
    const jsonText = pyodide.runPython('solve_to_json(WEB_INPUT_TEXT)');
    postStatus(4, '生成输出结果', 96);
    const payload = JSON.parse(jsonText);
    rememberResult(cacheKey, payload);
    self.postMessage({ type: 'result', id, payload });
  } catch (error) {
    self.postMessage({ type: 'error', id, message: error && error.message ? error.message : String(error) });
  }
};
