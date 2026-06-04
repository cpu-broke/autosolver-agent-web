# AutoSolver Agent 前端使用与部署说明

这个文件夹是给评委打开的网页前端，适合免费部署到 GitHub Pages。

你可以把它理解成“操作界面”：评委打开页面后，可以上传赛题 `.txt` 文件，点击求解，在页面里看到表格结果，并下载结果文件。

当前主流程仍然是：

```text
GitHub Pages 前端 + Hugging Face Spaces 免费后端
```

真正运行 Python 算法的地方不在 GitHub Pages。GitHub Pages 只能放静态网页，不能运行 Python 后端。Python 后端在 `hf_space/` 文件夹里，建议部署到 Hugging Face Spaces 免费 CPU 环境。

## 一、整体结构

```text
D:\Auto_Solver
├─ autosolver_web\   # 前端网页，部署到 GitHub Pages
└─ hf_space\         # 后端服务，部署到 Hugging Face Spaces
```

访问链路是：

```text
评委浏览器
  -> 打开 GitHub Pages 页面
  -> 前端把 txt 内容发给后端 API
  -> Hugging Face Spaces 后端调用 Python 算法
  -> 后端返回结果
  -> 前端展示表格并提供下载
```

你最终只需要把 GitHub Pages 链接发给评委。评委不需要安装 Python，也不需要打开 Hugging Face 后端链接。

## 二、前端文件说明

```text
autosolver_web/
├─ index.html             # 页面结构
├─ styles.css             # 页面样式和动效
├─ app.js                 # 上传、求解、缓存、取消、下载等交互逻辑
├─ solver-worker.js       # 备用 Pyodide worker，当前主流程不依赖它
├─ solver.py              # 备用纯前端求解时使用的算法文件
├─ sample/
│  └─ large_seed301.txt   # 示例数据
├─ .nojekyll              # GitHub Pages 辅助文件，保留即可
└─ README.md              # 当前说明文件
```

你最需要关注的是：

- `app.js` 第一行附近的 `DEFAULT_API_BASE_URL`：填写你的后端地址。
- `sample/large_seed301.txt`：页面里的示例数据，建议保留，方便评委一键体验。

## 三、先部署后端，再部署前端

建议顺序：

1. 先把 `hf_space/` 部署到 Hugging Face Spaces。
2. 得到后端地址，例如：

```text
https://your-autosolver-space.hf.space
```

3. 把这个地址填到 `autosolver_web/app.js`。
4. 再把 `autosolver_web/` 部署到 GitHub Pages。

原因：前端需要知道后端地址，才能把赛题数据发过去求解。

## 四、配置后端 API 地址

打开：

```text
autosolver_web/app.js
```

找到：

```js
const DEFAULT_API_BASE_URL = 'https://your-autosolver-space.hf.space';
```

改成你自己的 Hugging Face Space 地址，例如：

```js
const DEFAULT_API_BASE_URL = 'https://autosolver-agent-demo.hf.space';
```

注意：

- 不要在最后加 `/`。
- 不要写成 `/api/health`。
- 不要写成 `/api/solve`。
- 正确格式是 `https://xxx.hf.space`。

如果暂时不想改代码，也可以打开页面后点击右上角 `API` 按钮，在弹窗里填写后端地址。但发给评委前，推荐直接改 `app.js`，这样评委打开就能用。

## 五、本地预览前端

进入前端目录：

```powershell
cd D:\Auto_Solver\autosolver_web
```

启动静态服务器：

```powershell
python -m http.server 8000
```

浏览器打开：

```text
http://localhost:8000
```

不要直接双击 `index.html`，因为 `file://` 模式下读取示例文件等功能可能受限制。

## 六、部署到 GitHub Pages

推荐新建一个专门的 GitHub 仓库，例如：

```text
autosolver-agent-web
```

把 `autosolver_web/` 里面的文件上传到仓库根目录。上传后，仓库根目录应该直接看到：

```text
index.html
styles.css
app.js
solver-worker.js
solver.py
sample/
.nojekyll
README.md
```

注意：不要把整个 `autosolver_web` 文件夹套进去。GitHub 仓库根目录应该直接看到 `index.html`。

然后：

1. 进入仓库 `Settings`。
2. 左侧找到 `Pages`。
3. 找到“构建和部署”。如果页面是英文，标题通常是 `Build and deployment`。
4. 发布来源选择“从分支部署”。英文界面是 `Deploy from a branch`。
5. 分支选择 `main`。
6. 目录选择 `/root`。
7. 保存，等待 GitHub Pages 生成链接。

最终链接类似：

```text
https://你的用户名.github.io/autosolver-agent-web/
```

这个链接就是发给评委的链接。

## 七、评委使用流程

评委打开页面后：

1. 页面会自动预热后端 Python 引擎。
2. 如果免费 Hugging Face Space 正在休眠，第一次可能需要等待几十秒。
3. 点击“选择赛题文件”上传 `.txt`。
4. 也可以点击“载入示例数据”快速试用。
5. 点击“启动求解”。
6. 如果这份输入和最近求解过的内容完全一样，会直接命中前端缓存，很快显示结果。
7. 如果是新输入，前端会请求后端运行 Python 算法。
8. 求解过程中可以点击“取消”，页面会停止等待本次结果。
9. 求解完成后，结果显示在表格里。
10. 可以搜索订单或骑手。
11. 可以复制或下载结果。

## 八、体验优化说明

### 1. 后端预热

页面打开后会自动请求：

```text
GET /api/health
```

这样用户上传文件时，免费后端通常已经开始唤醒。

页面状态会显示：

```text
Python 引擎预热中
```

### 2. 最近 8 次结果缓存

前端会缓存当前页面会话中最近 8 次完全相同输入的结果。

效果是：

```text
同一个 txt 再次点击求解
-> 命中前端缓存
-> 直接展示结果
-> 不再重新请求后端
-> 不再重新跑 Python
```

缓存 key 使用输入内容的 SHA-256 指纹，不会把整份大 txt 当成 key 保存。

注意：

- 缓存只在当前浏览器页面里有效。
- 刷新页面后缓存会消失。
- 输入内容必须完全一致才会命中缓存。
- 改一个字符、换一行、重新生成文件，都可能导致缓存不命中。

### 3. 取消按钮

求解过程中可以点击“取消”。

取消后：

- 页面停止等待本次请求。
- 按钮恢复可点击。
- 状态显示“已取消”。
- 旧结果不会被强行清空。

注意：取消主要是改善前端体验。后端如果已经开始计算，可能仍会在服务器上自己跑完，但页面不会继续卡住。

### 4. 表格最多渲染前 200 行

为了避免以后结果变多导致页面卡顿，表格最多渲染前 200 行。

这不会影响下载：

- 页面表格：最多显示前 200 行。
- 复制 TXT：包含完整结果。
- 下载 TXT：包含完整结果。
- 下载 JSON：包含完整结果。

如果结果超过 200 行，表格底部会提示“复制和下载仍包含完整结果”。

### 5. 备用 Pyodide worker 缓存

当前正式推荐流程是 Hugging Face 后端求解，不依赖 Pyodide。

不过项目保留了 `solver-worker.js`，方便以后切回纯前端求解。这个 worker 也做了缓存优化：

```js
fetch('./solver.py?v=v30-trim-cycle-cache', { cache: 'force-cache' })
```

并且 worker 内也缓存最近 8 次完全相同输入的结果。

如果以后更新算法版本，建议同步修改版本号，例如：

```text
v31-new-solver
```

## 九、结果说明

结果表格包括：

- 序号
- 订单 `task_id_list`
- 分配骑手 `courier_id`
- 骑手数

右侧“原始输出”是下载 TXT 的内容，格式类似：

```text
T0037	C075,C074
T0039	C014,C048
```

`下载 TXT` 是最适合赛题提交的格式。

## 十、常见问题

### 问题 1：页面显示“待配置 API”

说明前端还不知道后端地址。

解决：

1. 确认 Hugging Face Space 已部署完成。
2. 复制 Space 地址，例如 `https://xxx.hf.space`。
3. 打开网页右上角 `API`。
4. 粘贴地址并保存。

更推荐直接改 `app.js` 里的 `DEFAULT_API_BASE_URL`。

### 问题 2：页面显示“正在唤醒”很久

免费 Hugging Face Space 长时间没人访问后会休眠。

可以打开：

```text
https://你的-space.hf.space/api/health
```

如果看到：

```json
{"status":"ok","engine":"ready"}
```

说明后端已经醒了。

### 问题 3：点击求解后失败

可能原因：

- 后端地址填错。
- Hugging Face Space 还没构建完成。
- 上传的文件格式不对。
- 输入内容为空。

建议先用“载入示例数据”测试。如果示例能跑，说明系统本身没问题。

### 问题 4：为什么第二次求解同一个文件特别快

这是前端缓存命中了，是正常现象。

同一个浏览器页面里，最近 8 次完全相同输入会缓存结果。再次点击“启动求解”会直接显示上一次结果，不再请求后端。

### 问题 5：GitHub Pages 打开后样式不对

检查仓库根目录是不是直接有：

```text
index.html
styles.css
app.js
```

如果它们被放在 `autosolver_web/` 子文件夹里，而 Pages 配置又是 `/root`，页面可能找不到文件。

## 十一、最终检查清单

发给评委前，建议你自己检查：

- [ ] Hugging Face Space 的 `/api/health` 能打开。
- [ ] `autosolver_web/app.js` 里的 `DEFAULT_API_BASE_URL` 已经改成真实 Space 地址。
- [ ] GitHub Pages 页面能正常打开。
- [ ] 页面打开后右侧状态能进入预热或就绪状态。
- [ ] 点击“载入示例数据”后能看到文件信息。
- [ ] 点击“启动求解”后能得到结果表格。
- [ ] 再次点击“启动求解”同一份输入，能很快命中缓存。
- [ ] 求解过程中点击“取消”，页面状态能恢复。
- [ ] “下载 TXT” 能下载完整结果文件。
- [ ] 把 GitHub Pages 链接发给别人测试，不需要你本机开任何服务也能用。

## 十二、最终发给评委哪个链接

只发 GitHub Pages 前端链接，例如：

```text
https://你的用户名.github.io/autosolver-agent-web/
```

不要发 Hugging Face Space 后端链接。后端链接只是给前端调用的，评委不需要直接操作它。
