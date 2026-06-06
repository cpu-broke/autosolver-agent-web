# AutoSolver Agent 技术文档

## 1. 系统架构

AutoSolver Agent 是前后端分离的配送分配求解系统。

```text
Web 前端
  -> HTTP API
    -> FastAPI 后端
      -> solver.py 求解算法
```

前端负责数据导入、交互状态、结果展示、结果缓存和文件导出。后端负责接收输入文本、调用 Python 求解算法并返回结构化结果。核心优化逻辑集中在 `solver.py`。

## 2. Web 前端技术

前端使用原生 Web 技术实现：

```text
HTML5 + CSS3 + JavaScript ES6
```

主要文件：

```text
index.html          页面结构
styles.css          页面布局、视觉样式、动态交互
app.js              前端业务逻辑
solver-worker.js    备用 Web Worker
solver.py           备用同源求解脚本
sample/             示例数据目录
```

核心功能：

```text
本地文本文件读取
后端预热
求解请求
请求取消
结果缓存
历史求解记录
表格渲染
TXT / JSON 导出
```

前端使用 `File API` 读取本地文本文件，使用 `Fetch API` 调用后端接口，使用 `Blob` 生成可下载结果文件，使用 `Web Crypto API` 计算输入文本哈希。

## 3. 前端缓存机制

前端缓存最近 8 次完全相同输入的求解结果。

缓存 key 由以下内容组成：

```text
solver 版本号 + API 地址 + 输入文本 SHA-256
```

当用户重复求解同一个数据集时，前端可以直接复用缓存结果，避免重复调用后端。

## 4. 后端技术

后端使用：

```text
FastAPI + Uvicorn + Python
```

后端核心接口：

```http
GET  /api/health
POST /api/solve
```

`/api/health` 用于服务状态检查和前端预热。  
`/api/solve` 接收输入文本，调用 `solver.py`，返回结构化结果、原始文本输出和运行统计信息。

求解接口输入：

```json
{
  "filename": "large_seed301.txt",
  "input_text": "..."
}
```

求解接口输出：

```text
rows         表格展示用结构化结果
output_text  原始文本结果
stats        运行时间、输出行数、订单数、骑手数、输入行数
```

后端单次求解使用单线程执行器运行，避免多个大任务同时占满免费 CPU 资源。输入长度限制为 5,000,000 字符，单次求解超时限制为 45 秒。

## 5. 输入数据模型

输入数据每行表示一个候选分配方案，典型字段为：

```text
task_id_list    courier_id    total_score    willingness
```

字段含义：

```text
task_id_list    订单或合单任务 ID
courier_id      候选骑手 ID
total_score     候选方案预测分数
willingness     骑手接单概率
```

算法将订单 ID 和骑手 ID 映射为整数编号。订单集合使用 bitmask 表示：

```python
mask |= 1 << tid
```

bitmask 用于快速判断任务冲突、合并覆盖集合和统计覆盖订单数。同一任务集合与同一骑手对应的重复候选会被压缩，只保留期望成本最低的候选。

## 6. 目标函数

算法以期望成本作为候选方案评价指标。

单个候选方案成本：

```python
cost = p * score + (1.0 - p) * BASE * k
```

其中：

```text
p      接单概率
score  成功接单时的预测分数
BASE   失败或未覆盖时的基准惩罚
k      候选方案覆盖的订单数量
```

当前 `BASE` 为：

```python
BASE = 100.0
```

解的比较优先级：

```text
1. 覆盖订单数更多
2. 期望成本更低
3. 分配组数量更少
```

## 7. 求解算法策略

当前 `solver.py` 使用场景自适应的多策略组合求解方法。它不是只使用单一贪心或单一匹配，而是先生成多个候选解，再根据覆盖数量、期望成本和输出结构选择最优方案。

整体流程：

```text
解析输入
压缩重复候选
统计场景特征
生成候选解池
选择唯一覆盖基础解
构造多骑手备选输出
按场景执行局部修复
返回最终分配结果
```

### 7.1 输入解析与候选压缩

`_parse()` 将文本行解析为候选对象，记录：

```text
任务集合 mask
骑手编号 cidx
原始 task 字符串
原始 courier 字符串
score
p
k
cost
gain
```

其中 `gain = BASE * k - cost`，表示相对于全部失败惩罚的收益。

`_compress()` 会以 `(mask, cidx)` 为键压缩重复候选。同一个任务集合分配给同一个骑手时，只保留 `cost` 最低的一条，减少后续搜索规模。

### 7.2 场景识别

`_stats()` 根据候选数据的概率分布、候选覆盖密度、骑手资源密度和有效候选覆盖情况识别场景。当前实现不是简单按任务数量或骑手数量划分，而是使用分位数、均值和多条件投票组合判断。

主要场景标记包括：

```text
small           小规模场景
low             低接单概率场景
scarce          候选或骑手资源稀缺场景
route_scarce    有效路线覆盖不足场景
```

这些标记用于控制后续策略分支。它们不是完全互斥的标签，`solve()` 会在原始统计结果基础上进一步生成 `search_st`，把强稀缺和路线稀缺合并到搜索用的稀缺判断中。

场景识别使用的核心统计量包括：

```text
avg_p           接单概率均值
q10_p           接单概率 10% 分位数
q25_p           接单概率 25% 分位数
med_p           接单概率中位数
avg_task_options    平均每个任务候选数
q25_task             任务候选数 25% 分位数
avg_courier_options 平均每个骑手候选数
q25_courier          骑手候选数 25% 分位数
bundle_ratio         合单候选占比
q10_eff / q25_eff    有效候选骑手覆盖数分位数
q25_all              全部候选骑手覆盖数 25% 分位数
q25_single           单任务有效候选骑手覆盖数 25% 分位数
eff_courier_count    有效骑手数量
```

其中“有效候选”不是所有候选，而是满足以下任一条件的候选：

```text
单位成本低于 96
或候选收益 gain 大于 4
或接单概率大于 0.18 且单位 score 低于 70
```

`small` 的判断相对直接：

```text
task_count <= 18
```

`low` 使用接单概率分布判断，满足以下任一条件即认为是低概率场景：

```text
avg_p < 0.24
或 med_p < 0.22 且 q25_p < 0.12
或 q10_p < 0.04 且 q25_p < 0.15
```

`scarce` 使用投票式判断。以下稀缺信号中至少命中 2 个，才认为基础资源稀缺：

```text
任务数 / 骑手数 > 1.1
avg_task_options < 120
q25_task < 60
avg_courier_options < 80
bundle_ratio > 0.55 且 q25_courier < 45
```

`route_scarce` 用于识别大规模非低概率场景中的有效覆盖不足。它要求：

```text
不是 low 场景
且 task_count >= 35
且满足有效骑手数、有效覆盖分位数或单任务有效覆盖不足等条件之一
```

具体触发条件包括：

```text
courier_count <= task_count * 1.55
或 eff_courier_count <= task_count * 1.35
或 q25_eff <= 18
或 q10_eff <= 10
或 q25_single <= 8
或 scarce 已成立且 q25_all <= 32
```

场景识别会影响搜索宽度、多骑手备选数量和局部修复策略。例如 `low` 场景会更重视多骑手备选，`route_scarce` 场景会更重视覆盖修复，`small` 场景会启用更精细的精确搜索。

### 7.3 基础候选解池

`solve()` 首先构造候选解池 `pool`。候选解池保存不同策略得到的基础解，最后统一比较。不同策略不是所有场景都会执行，而是由 `task_count`、`low`、`route_scarce` 和剩余时间共同决定。

实际分支关系如下：

```text
所有有效输入：
  _mcmf_single()

task_count <= 18：
  _exact_small_unique()
  _exact_small_dp_unique()

task_count <= 8：
  _small_multi_group_exact_output()

非大规模普通场景：
  _greedy_candidates()

low 或 route_scarce：
  _row_first_candidate()
  _row_option_beam_output()

low：
  _multi_potential_candidate()
  _multi_bundle_first_candidate()
  _multi_model_beam_candidate()

route_scarce 且不是 low：
  _beam_cover_unique()
```

其中“大规模普通场景”指非 `low`、非 `route_scarce` 且 `task_count >= 35` 的场景。该场景会跳过部分普通贪心，以减少无效搜索，把时间留给快速多骑手输出和后续修复。

候选解会经过 `_clean()` 去除任务冲突，再用 `_key()` 比较优劣。比较重点是覆盖更多任务、期望成本更低、输出组数更少。

### 7.4 单骑手匹配基线

`_mcmf_single()` 构造单骑手分配基线。该策略把候选分配看作带成本的匹配问题，用最小费用最大流思想优先获得覆盖稳定、成本较低的基础结果。

该结果通常作为候选池里的基线解：

```text
single_c100_mcmf
```

它不一定是最终结果，但为后续贪心、精确搜索和多骑手输出提供稳定参照。

### 7.5 小规模精确搜索

当任务数 `task_count <= 18` 且剩余时间足够时，算法启用小规模精确策略：

```text
_exact_small_unique()
_exact_small_dp_unique()
```

当任务数 `task_count <= 8` 时，还会尝试：

```text
_small_multi_group_exact_output()
```

这类策略会更充分地枚举或动态规划局部组合，适合小数据集下追求更优解。所有精确搜索都受 deadline 控制，不会无限运行。

### 7.6 多排序贪心

`_greedy_candidates()` 只在未被 `skip_large_normal_greedy` 跳过时执行。也就是说，对于 `low` 或 `route_scarce` 场景，以及中小规模普通场景，会生成多组贪心候选；但对于非 `low`、非 `route_scarce` 且 `task_count >= 35` 的大规模普通场景，会跳过这部分普通贪心。

不同排序指标会带来不同解结构，例如：

```text
期望成本
接单概率
预测分数
单位覆盖成本
收益 gain
```

多排序贪心的作用是快速覆盖大部分任务，并为后续局部修复提供多个起点。跳过大规模普通场景的贪心，是为了避免在候选量很大但场景并不稀缺时消耗过多时间。

### 7.7 低概率场景策略

当 `_stats()` 判断为 `low` 场景时，算法会额外生成强调多骑手备选和失败风险控制的候选：

```text
_row_first_candidate()
_multi_potential_candidate()
_multi_bundle_first_candidate()
_multi_model_beam_candidate()
_row_option_beam_output()
```

低概率场景下，单个骑手接单失败风险较高，因此算法会优先寻找同一任务集合下的多个备选骑手，通过降低整体失败概率提升结果稳定性。

低概率场景的最大备选骑手数为：

```python
MULTI_LOW_MAX_RIDERS = 8
```

### 7.8 稀缺与路线覆盖不足场景策略

`scarce` 和 `route_scarce` 在代码里的作用不同。

`scarce` 是资源稀缺标记，主要影响：

```text
search_st 中的稀缺判断
多骑手备选参数
多候选输出选择时间片
后续修复策略的分支判断
```

`route_scarce` 是路线有效覆盖不足标记，会触发更偏覆盖修复的候选生成。主流程中，当 `low` 或 `route_scarce` 成立时，会尝试：

```text
_row_first_candidate()
_row_option_beam_output()
```

当 `route_scarce` 成立且不是 `low` 场景，并且剩余时间足够时，还会尝试：

```text
_beam_cover_unique()
```

进入输出后处理阶段后，`route_scarce` 会使用：

```text
_scarce_shadow_bundle_exact()
```

这类策略会优先处理候选少、骑手少或有效覆盖不足的任务，避免基础解在局部最优中漏掉难覆盖订单。

稀缺场景下多骑手备选会更保守，最大备选骑手数为：

```python
MULTI_SCARCE_MAX_RIDERS = 2
```

### 7.9 合单收益策略

算法会识别覆盖多个订单的合单候选，并比较合单方案与拆分方案的期望成本差异。

`_bundle_savings_unique()` 会在基础解完整覆盖时尝试用合单候选替换部分单订单候选。替换只有在覆盖不下降且期望成本更低时才会被接受。

合单策略的作用是：

```text
减少分配组数量
提升多订单覆盖效率
降低组合期望成本
保留有收益的合单候选
```

### 7.10 多骑手备选输出

基础解选出后，算法会构造最终输出格式。当前启用：

```python
SCENE_ADAPTIVE_MULTI_COURIER = True
```

多骑手组的失败概率为：

```text
fail = Π(1 - p_i)
```

对应期望成本由 `_group_expected_cost()` 计算。该函数会综合多个备选骑手的失败概率、成功分数和失败惩罚，并在单次求解过程中使用安全缓存，避免重复计算同一组候选。

不同场景的多骑手参数如下：

```text
低概率场景：最多 8 个备选骑手，最小收益阈值 0.01
普通场景：最多 4 个备选骑手，最小收益阈值 0.5
稀缺场景：最多 2 个备选骑手，最小收益阈值 6.0
```

普通大规模场景会优先使用 `_safe_output_multi()` 快速构造输出。低概率、小规模或稀缺场景会使用 `_choose_best_multi_output()` 在多个候选输出之间选择期望成本更低的方案。

### 7.11 输出后处理与局部修复

得到多骑手输出后，算法会按场景执行后处理：

```text
低概率场景：
  _low_global_backup_matching()

路线稀缺场景：
  _scarce_shadow_bundle_exact()

普通场景：
  _reassign_fixed_skeleton()
  _cycle_reassign_fixed_skeleton()
  _window3_fast_exact_repair_output()
  _local3_exact_refine()
```

这些步骤的目标不是从零开始求解，而是在已有输出结构上做局部替换、循环重分配和小窗口精确修复。新结果只有在覆盖不下降且期望成本降低时才会被接受。

### 7.12 时间预算控制

算法设置全局时间预算：

```python
TIME_LIMIT = 7
```

主流程中使用 deadline 控制每个策略的执行：

```python
deadline = start + TIME_LIMIT
```

各搜索策略会根据剩余时间决定是否继续执行。较耗时的策略会设置更短的局部 deadline，例如小规模精确搜索、Beam Search、多骑手输出选择和局部修复都具有独立时间片。

这种设计保证了算法能在 Web 请求场景下稳定返回，同时尽量利用剩余时间改善结果。

## 8. 结果格式

后端会将 `solver.py` 的结果转换为前端表格格式：

```json
[
  {
    "task": "T0030",
    "couriers": ["C047", "C046"]
  }
]
```

同时生成 TXT 输出：

```text
T0030    C047,C046
```

前端复制、下载 TXT、下载 JSON 和结果表格均基于该结构。
