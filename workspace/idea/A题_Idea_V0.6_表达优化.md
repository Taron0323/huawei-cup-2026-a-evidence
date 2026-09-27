# A题 Idea V0.6：驻留域划分、有限局部改进与 FIFO Cache 感知调度

题目：2026 年“华为杯”中国研究生数学建模竞赛 A 题《通用神经网络处理器下的多核调度问题》  
版本：V0.6（表达优化与算法定点修订）  
日期：2026-09-24  
阶段：Idea 设计与静态核对；不包含求解器开发、官方计时、批量评估或正式提交。

## 1. 一段话讲清 Idea

每个计算图都要在有限的 L1/UB 容量、两条计算 Pipe、DDR 搬运和跨核同步之间取平衡。我们的方案先把“哪些操作可以连续复用同一份片上张量”表示成驻留域，再分别为三个场景决定子图归属、核心归属和核内顺序：问题 1 以子图为独立 Task，问题 2 把同核子图合并成一个 Task，问题 3 在问题 2 的结构上按官方 FIFO Cache 事件判断重复输入是否命中。每张图独立、所有候选的生成顺序和上限固定。先用计算依赖、Pipe 负载、驻留域搬运和容量压力做轻量筛选，再对有限的初始方案和局部改进方案调用官方 Step1--3 与事件模拟；最终按真实 Makespan，再按真实新增搬运量 $Q^{\rm add}$ 选择。第一阶段 V1 只用固定起点取得全部正式覆盖，第二阶段 V2 在同一预算内加入多轮有界局部改进，因此可以先得到可交结果，再判断局部改进是否值得保留。

## 2. 题意、真实决策与主要瓶颈

### 2.1 输入、提交字段和三种执行机制

输入是一个带操作、逻辑张量和边的有向无环图。操作带有 `pipe` 与 `cycles`，张量带有存储位置和字节数。提交接口只有两个字段：

- `node_to_subgraph`：每个非 `COPY_IN`/`COPY_OUT` 操作恰好归属一个子图；
- `core_schedules`：每个子图恰好出现在一个核心的列表中，列表顺序是同核提交顺序。

操作发射时刻、Step2 的换出对象、Reload 次序和 Cache 状态由官方评估器生成，不能作为提交变量自行填写。空核允许出现在核心接口中，但不能把空核当作已经证明的加速来源。

| 机制 | 问题 1（A） | 问题 2（B） | 问题 3（C） |
|---|---|---|---|
| 驻留域 | 每个子图是一个独立 Task | 同核子图合并为一个 Task | 与 B 相同 |
| 同核跨子图数据 | 仍经 DDR；同核相邻 Task 至少等待 100 cycles | 可在片上复用，容量不足时由 Step2 插入 Spill/Reload | 与 B 相同，并由只读 FIFO Cache 服务命中 COPY_IN |
| 跨核就绪 | 前驱 Task 完成后再加 1000 cycles | 源 COPY_OUT 完成后，目标 COPY_IN 至少等待 500 cycles | 同 B |
| 片上容量 | 每核 L1=524288 bytes，UB=131072 bytes | 相同 | 相同 |
| 共享带宽 | DDR 读写共用 60 bytes/cycle | 相同 | DDR 仍为 60 bytes/cycle；Cache 为 1048576 bytes、250 bytes/cycle |
| Cache 规则 | 无 | 无 | 只有 `COPY_IN` 查询；命中不刷新 FIFO 顺序，未命中完成后尝试插入，容量不足时先进先出淘汰 |

官方执行链按以下顺序展开：校验方案；重建边界 COPY；Step1 生成核内访问序；B/C 按核心列表稳定分桶；Step2 插入 Spill/Reload；Step3 生成逐 Pipe 顺序和内存复用依赖；检查扩展执行图无环；最后做事件模拟。`schedule_step3.py` 使用 M、V、MTE2、MTE3 四类 Pipe，并把容量额度产生的 WAR/WAW 关系写入执行图。商图无环只能说明提交层合法，不能代替加入 COPY、Pipe FIFO 和内存复用依赖后的最终执行检查。

### 2.2 已核对的输入结构

本轮对附件 `data/case_001.json`--`case_100.json` 做了只读 JSON 读取和计算依赖图统计，没有调用 Step1--3 或官方评估器。非 COPY 计算操作数、张量数与计算依赖弱连通分量数的最小值、中位数、最大值如下：

| 静态量 | 最小值 | 中位数 | 最大值 |
|---|---:|---:|---:|
| 计算操作数 $n$ | 552 | 3720.5 | 35705 |
| 原张量数 | 816 | 4590.5 | 40287 |
| 计算依赖弱连通分量数 | 1 | 39.5 | 2666 |
| 计算依赖最长路 $L_G$（cycles） | 400 | 6140 | 863040 |
| 单个图输入的最大计算扇出 | 1 | 24 | 2666 |
| $Q^{\rm orig}/(60\max\{W_M,W_V\})$ | 0.000849 | 0.050138 | 0.259988 |
| $W_M/W_V$（100 图，$W_V>0$） | 0 | 2.103014 | 24.957652 |
| 最大单张量/L1 容量（非 DDR 张量） | 0 | 0.024902 | 0.5625 |
| 最大单张量/UB 容量（非 DDR 张量） | 0 | 0.035156 | 0.25 |
| 最大单张量/默认 Cache 容量（非 DDR 张量） | 0.000977 | 0.012451 | 0.28125 |

弱连通分量数小于核数的用例数为：

| 核数 $K$ | 分量数小于 $K$ 的用例数 | 解释 |
|---:|---:|---|
| 2 | 16 | 这些图没有两条计算依赖弱连通分量可直接一一分核 |
| 3 | 16 | 与 K=2 相同，最低分量数为 1，未出现恰好等于 2 的用例 |
| 4 | 16 | 仍需从公共前段、可并行支路或块边界取得额外起点 |
| 5 | 16 | 不能把“分量数不少于 K”作为默认前提 |

`case_016` 是大图代表之一：17995 个计算操作、1 个计算依赖弱连通分量、最大图输入扇出 305。单分量不等于不可并行。它可能包含公共前段、扇出支路和汇合后段；但若前缀诱导图始终只有一个连通分量，沿深度寻找“分量数不少于 K”的条件就不会给出切层。求解器因此把分支边界作为候选来源，找不到满足条件的合法切点时保留少量块或退回 A0/B0，而不是强行制造 K 个分量。

原始 JSON 中 COPY 操作的 `cycles` 为 0，这是字段占位；Step3 按关联张量字节和带宽重算 COPY 持续时间。普通计算操作的 cycles 全为正。Step2 的 victim、backing 和 Spill 记录由官方实现决定，不能从原始 `cycles=0` 推断零搬运。

100 个原图均没有直接的 op→op 边，且每个逻辑张量至多有一个非 `COPY` 生产者；下文的驻留域简式按这一官方输入结构书写，多消费者由集合基数计数。若扩展到直接 op→op 边或多生产者张量，应先按对应场景的构图规则补入 `data_size` 或生产域/消费域 COPY，再重新计量，不能继续套用单生产者简式。

### 2.3 瓶颈的量纲

令 $W_M$、$W_V$ 为 M、V 计算周期总和，$L_G$ 为原计算依赖最长路，$Q^{\rm orig}$ 为输入与输出原始 COPY 的字节总数。DDR 与最大计算 Pipe 的下界比值定义为

$$
r=\frac{Q^{\rm orig}}{60\max\{W_M,W_V\}}.
$$

将计算分摊到 $K$ 核后，必要 DDR 下界严格超过最大计算 Pipe 下界的条件是 $r>1/K$。这只比较两个必要下界：实际尾部、跨核等待、重复图输入、Spill、动态带宽共享和 FIFO 淘汰仍会改变 Makespan。$r$ 较小不能推出 Cache 没有收益，$r$ 较大也不能直接断言实测运行受 DDR 限制。

按静态下界比较，100 图中 $r>1/K$ 的用例数为：K=2 为 0，K=3 为 0，K=4 为 1（`case_012`），K=5 为 2（`case_012`、`case_044`）。这些数字只说明必要项的相对强弱。

每个用例后续都报告 $T_1/LB_1$ 与
$L_G/(\max\{W_M,W_V\}/K)$。其中统一单核基准 $T_1$ 由 `singlecore_evaluate.py` 在后续第一轮官方计时和评估中取得，本轮不填写。$LB_1$ 是下节定义的必要下界。由静态结构提出的“负载均衡、依赖路径和 Spill 是主要优化方向”属于机制判断，须由正式执行结果检查。

## 3. 相关方法及本题的改动

本方法保留两篇已读原始论文作为直接方法背景：

1. Merten Popp, Sebastian Schlag, Christian Schulz, Daniel Seemaier, *Multilevel Acyclic Hypergraph Partitioning*, arXiv:2002.02962v2, 2020，正文第 1--7 页，§2、§3.1--§3.3。本文借鉴有向超图、商图无环和边界迁移的组织方式；本题仍须按每个接收域重算 COPY，不能把超边连通度直接当作执行时间。
2. Sebastian Schlag, Vitali Henne, Tobias Heuer, Henning Meyerhenke, Peter Sanders, Christian Schulz, *k-way Hypergraph Partitioning via n-Level Recursive Bisection*, ALENEX 2016, pp.53--67；arXiv:1511.03137v1，正文第 1--3、5--6 页 §4.3--§4.4。本文借鉴多起点和受影响边界的局部更新；本题的方向依赖、容量状态与官方 Pipe 递推仍需单独检查。

另外三组文献用于界定术语和对照范围。本轮对 HEFT、Graham 和 Belady 只核对了书目信息及可访问摘要/公开入口，没有用未读取的正文页码支持本题公式。

- Topcuoğlu, Hariri, Wu, *Performance-Effective and Low-Complexity Task Scheduling for Heterogeneous Computing*, IEEE TPDS 13(3), 2002, pp.260--274。HEFT 的向上秩和最早完成位置提供列表调度背景；本方案的 H 序只作为轻量起点，不称为 HEFT 复现，也不把其代价模型用于正式计时。
- Graham, *Bounds on multiprocessing timing anomalies*, SIAM Journal on Applied Mathematics 17(2), 1969, pp.416--429；以及 Graham, Lawler, Lenstra, Rinnooy Kan, *Optimization and Approximation in Deterministic Sequencing and Scheduling: a Survey*, Annals of Discrete Mathematics 5, 1979, pp.287--326。它们用于说明列表调度和调度异常的背景。它们不能代替本题空核等价性的代码分析，也不能据此宣称多核曲线单调。
- Belady, *A Study of Replacement Algorithms for a Virtual-Storage Computer*, IBM Systems Journal 5(2), 1966, pp.78--101。它提供离线替换研究背景。官方 Step2 的张量大小、已有 DDR backing、重复 Reload 与多类容量状态不等同于单一等长页缓存，因此这里只把随附源码和 `docs/核内调度算法.md` 中的 `next_use` 排序视为官方实现事实，不宣称 Step2 在本题完整执行模型下全局最优；问题 3 的 Cache 明确是 FIFO，不能改写为 LRU 或 Belady 缓存。

前两篇论文承担本方案的结构依据；后三组只承担背景和术语边界。未取得全文的文献不用于本题关键公式或效果结论。

## 4. 统一主线、确定性与 V1/V2 关系

### 4.1 唯一默认协议

入口概念为 `solve_case(G, K, scene, fixed_budget)`。一张图的候选只依赖该图、请求核数、场景、`config.txt` 和固定版本。用例分位数、机器瞬时负载、剩余墙钟和其他图的赢家不改变候选机会。所有列表排序按整数 ID、核心号、结构编码和规范化 `plan_key` 破同分；失败保留失败类别并占用该槽位。

候选经历四层：

1. **构造层**：一次建立操作邻接、张量生产者/去重消费者、弱连通分量、H/R 路径、M/V 工作量和输入消费域。
2. **轻量层**：每个候选做合法性检查、域计数差量更新、核序回放、代理时间、资源池工作量和去重。轻量回放不是免费操作，也不等于 profile。
3. **profile 层**：按官方边界构图、Step1、Step2、Step3，保存扩展图、Pipe 序、容量状态、Spill/Reload 和局部参考量。
4. **官方评估层**：调用完整事件模拟，按真实 `(Makespan, Q_add)` 选择正式结果。

候选进入第一槽或第二槽、普通与容量通道的接受条件、V1/V2 的状态复用、失败占位和停止规则只在 §6.3--§6.4 定义一次；§7 只补充 A/B/C 的机制差异，§9 只记录覆盖、成本和待测状态。

### 4.2 V1 先覆盖全量，V2 再做局部改进

默认关系固定为：

- **V1**：每个正式输入、场景和核数使用规定起点，完成第一槽官方评估。V1 独立覆盖 100 个用例、统一单核 $T_1$、A 的 K=2--5、B 的 K=1--5 和 C 的 K=1--5（C 使用同一 B 计划的固定结构）。V1 在所有第一槽结果写入后才结束。
- **V2**：读取 V1 保存的组合状态，其中已固定初始候选集合、第一槽计划、prepared 状态和 V1 的补空来源；在相同图内按固定规则做多轮轻量改进，局部候选只使用第二槽。V2 的默认第一槽就是 V1 的第一槽，因而同计划可以精确复用；第二槽是 V2 的局部或结构补位候选。对 C，V2 冻结 V1 在同一 K 的 B 赢家 $X_B^{\rm V1}$，沿用其 C 固定方案结果并最多评一个 C 挑战；V2 不换成新的 B 赢家。若后续要让 C 跟随 V2 的 B 赢家，必须另算一个 C 基线槽，不能继续使用 3590 上限。这个选择避免把“V1 独立热链”“V2 自己热链”和“严格无局部搜索消融”同时称为零额外调用。
- **严格独立消融**：若后续需要让 V1 和 V2 各自从独立上一核数赢家开始，两个首槽输入不同，不能复用 V1 的官方调用；它作为额外诊断，单独计费，不属于本默认 8 小时协议。

因此，V1 的可交性不依赖局部改进；V2 的改进收益比较的是“给定 V1 初始化与历史状态”的局部收益。它不替代完全移除局部搜索的独立算法消融。

### 4.3 空核扩展、单核保底与曲线处理

前一核数的成功计划可在当前 $K$ 接口中补空列表后作为一个候选。它合法且 Makespan 保持不变需要同时满足：计划字段只增加空核；`derive_multicore_plan` 的覆盖与唯一性仍成立；没有跨空核边；`validate_task_order`、核遍历顺序和所有 tie-break 不依赖空核产生的新事件；同一配置下扩展图、Pipe 和容量状态只包含原有操作。这个结论只对实际核接口和当前计划成立，不能由一个微图推广到所有 A/B，也不推广到 C 的 FIFO 事件。

A0/B0 将全部计算操作放入核 0 的一个子图。若该计划的完整输入边界与统一单核计划一致，K 核接口的其余核为空，且空核不会改变事件排序，则它与 $T_1$ 等价。该等价性分 A、B 分别检查；C 不继承这个结论，因为 Cache 查询次序、插入时刻和核心遍历可能改变。

默认保底流程如下：

1. 统一单核 $T_1$ 单独作为 V1 的单核基准；A 的正式主矩阵从 K=2 开始，K=2 的前缀候选可使用经等价检查的 $T_1$/A0 补空计划。B 的正式矩阵包含 K=1，B0 与 $T_1$ 的字段一致时可精确复用。
2. K>1 将上一 K-1 赢家补空核，和当前 K 的规定起点共同进入初始集合；若静态等价性检查通过且计划未改变，精确复用已有结果，否则在当前 K 补评一次。
3. 若当前 K 的新候选都失败，保留上一核数补空计划的实际结果；若补空计划也未取得等价证据，则以当前接口实际评估的结果为准。
4. 任何 K 的结果都按实际 `(F,Q_add)` 报告。失败、变慢或加速比低于 1 都保留，不用平滑、单调化或事后替换。

最小微图只验证所测计划；一般等价性由上述代码条件和每个正式计划的字段检查共同支撑。

## 5. 数学模型、执行递推和下界

### 5.1 方案变量与合法顺序

$V$ 是非 COPY 计算操作集合，$n=|V|$；$T_{\rm in}$ 是没有计算生产者的逻辑输入集合，$T_{\rm prod}$ 是计算生产结果集合；$b_t$ 为张量字节数；$C(t)$ 为去重计算消费者，$u(t)$ 为计算生产者；$q_v\in\{M,V\}$，$c_v=\max(1,\mathrm{cycles}_v)$ 为计算周期。方案写成

$$
X=(g,a,\sigma),
$$

其中 $g(v)$ 是子图归属，$a(s)$ 是子图所在核心，$\sigma_k$ 是核心 $k$ 的子图列表。

对至多 $n$ 个子图槽，$x_{v,s},h_s,y_{s,k}\in\{0,1\}$ 分别表示归属、槽启用和分核：

$$
\sum_s x_{v,s}=1,\qquad x_{v,s}\le h_s,\qquad
h_s\le\sum_vx_{v,s},\qquad\sum_k y_{s,k}=h_s.\tag{1}
$$

空槽不进入 `core_schedules` 的子图列表；空核可以没有列表项。

商图边变量不是自由的。定义

$$
b_{s,t}=\bigvee_{(u,v)\in E_{\rm calc}}
\left(x_{u,s}\land x_{v,t}\right),\qquad s\ne t,\tag{2}
$$

它只表示真实计算依赖是否跨块。仅加入
$b_{s,t}\ge x_{u,s}+x_{v,t}-1$ 会允许任意把 $b$ 置 1，不能用来计 COPY 或构图。若用 MILP 形式表达，给每个 $(u,v,s,t)$ 增加
$q_{uvst}\in\{0,1\}$，并使用

$$
q_{uvst}\le x_{u,s},\quad q_{uvst}\le x_{v,t},\quad
q_{uvst}\ge x_{u,s}+x_{v,t}-1,
$$

以及
$b_{s,t}\ge q_{uvst}$、$b_{s,t}\le\sum_{(u,v)}q_{uvst}$。实现中直接从归属映射派生布尔边，避免把不精确的下界当成执行语义。

商图秩可用作保守合法性筛选。对非空、不同槽 $s,t$，$0\le\rho_s\le n-1$，并满足

$$
\rho_t\ge\rho_s+1-n(1-b_{s,t}).\tag{3}
$$

同核序变量 $z^k_{s,t}=1$ 表示 $s,t$ 同在核心 $k$ 且 $s$ 在 $t$ 前。对不同槽使用

$$
\begin{aligned}
&z^k_{s,t}\le y_{s,k},\quad z^k_{s,t}\le y_{t,k},\\
&y_{s,k}+y_{t,k}-1\le z^k_{s,t}+z^k_{t,s}\le1,\\
&z^k_{s,t}+z^k_{t,w}-1\le z^k_{s,w}.
\end{aligned}\tag{4}
$$

题面 D.1 与 `validate_task_order` 的实际适用层是：A 要把商图边和每核列表相邻边合成图并检查无环；B/C 的提交列表影响稳定分桶和 Step1 次序，但不能把整个 A 的 Task 串行条件机械复制到 B/C。B/C 最终仍需 `validate_execution` 检查本地数据/内存依赖、Pipe FIFO 和跨核 COPY 的全局环。式（3）--（4）是搜索空间的保守约束，不取代最终扩展执行图。

### 5.2 驻留域与结构搬运

A 的输入接收域和计算结果外域分别为

$$
I_A(t)=\{g(v):v\in C(t)\},\quad
R_A(t)=\{g(v):v\in C(t),g(v)\ne g(u(t))\}.
$$

令 $r_A(t)=|R_A(t)|$，$o_t=1$ 表示存在原 `COPY_OUT` 或该结果无计算消费者。A 的基础结构搬运量是

$$
Q_A^0=\sum_{t\in T_{\rm in}}b_t|I_A(t)|+
\sum_{t\in T_{\rm prod}}b_t\left[r_A(t)+\mathbf 1\{r_A(t)>0\lor o_t=1\}\right].\tag{5}
$$

B/C 的接收域按核心计数：

$$
I_B(t)=\{a(g(v)):v\in C(t)\},\quad
R_B(t)=\{a(g(v)):v\in C(t),a(g(v))\ne a(g(u(t)))\}.
$$

每个远端接收核有一对 COPY，最终输出单独计入：

$$
Q_B^0=Q_C^0=\sum_{t\in T_{\rm in}}b_t|I_B(t)|+
\sum_{t\in T_{\rm prod}}b_t[2|R_B(t)|+o_t].\tag{6}
$$

这两个简式只在上一节所述的当前 100 个 JSON 输入结构下直接适用；多个消费者仍按接收域集合基数计数。若扩展到多生产者输入，需按 producer-domain/consumer-domain pair 重新展开；若出现直接 op→op 边，还要按官方 `data_size` 语义补入对应 COPY，不能直接套用式（5）--（6）。

$Q^{\rm orig}$ 按原图中 `COPY_IN` 输出和 `COPY_OUT` 输入的张量大小逐操作相加；它不是把逻辑张量数乘以消费者数。对每条实际 Spill 记录 $e$，$b_e$ 为恢复字节，$z_e=1$ 表示该次恢复前还需要新的 DDR 写回，则

$$
Q^{\rm spill}=\sum_e b_e(1+z_e),\quad
Q^{\rm sched}=Q^0+Q^{\rm spill},\quad
Q^{\rm add}=Q^{\rm sched}-Q^{\rm orig}.\tag{7}
$$

其中 `scheduled_copy_bytes` 对应 $Q^{\rm sched}$，`spill_added_copy_bytes` 对应 $Q^{\rm spill}$；$Q^{\rm add}$ 还要减去原图的 `original_graph_copy_bytes`，不能把它与单独的 Spill 字段混同。C 的 Cache 命中改变服务池，不改变结构 COPY 和 Step2 产生的 Spill；正式结果另从 `cache_stats` 与事件路径统计 DDR/Cache 服务字节。

### 5.3 容量和官方轨迹

给定 X，官方构图、Step1、Step2、Step3 确定扩展操作集合 $\mathcal O_X$、物理张量版本、Pipe 序和内存依赖。物理版本 $\tilde t$ 在输出申请时刻 $A_{\tilde t}$ 分配，在所有读者（包括 `COPY_OUT`）完成时刻 $L_{\tilde t}$ 释放。对每个核心 $k$、存储类型 $m\in\{L1,UB\}$ 和时刻 $\tau$，硬容量约束为

$$
\sum_{\tilde t:\,A_{\tilde t}\le\tau<L_{\tilde t}}
 b_{\tilde t}\mathbf 1\{\operatorname{core}(\tilde t)=k,\operatorname{mem}(\tilde t)=m\}
\le C_m.\tag{8}
$$

Step2 在官方确定序列中申请输出、释放末次使用输入并按 `next_use` 选择可换出对象；当前操作所需输入和输出不能作为该次 victim。已有 DDR backing 时 Reload 只新增读，没有 backing 时先写回再恢复。Step3 再把可拆分容量额度转成 WAR/WAW 依赖。Spill 是容量约束下的真实代价；理想活跃峰值超过容量只能作为轻量提示，不能填写成已发生 Spill。

令 $S_o,D_o$ 为扩展操作开始和完成时间，$F(X)=\max_{o\in\mathcal O_X}D_o$。计算依赖、Pipe FIFO、内存依赖和跨核 COPY 的确定性事件递推记为

$$
(S,D,\mathrm{memory},\mathrm{Cache})=
\Phi_r(\Psi_r(G,X);\theta).
$$

其中 $r\in\{A,B,C\}$，$\theta$ 来自原始 `config.txt`。A 的 Task 激活约束为

$$
B_s\ge\max\left\{0,\max_{t\in\operatorname{Pred}(s)}E_t,
\max_{\substack{t\in\operatorname{Pred}(s)\\a(t)\ne a(s)}}(E_t+1000),E_{p(s)}+100\right\},\tag{9}
$$

缺失项省略，根 Task 不额外加 100。B/C 的每条跨核连接满足

$$
S_{\rm COPY\_IN}\ge D_{\rm COPY\_OUT}+500.\tag{10}
$$

一次进入带宽池 $p$ 的搬运独占工作量为
$w_{e,p}=\max(1,\lceil b_e/B_p\rceil)$。池中有 $m_p(\tau)$ 个未完成搬运时，各任务按公平共享递推

$$
\frac{dR_e(\tau)}{d\tau}=-\frac1{m_p(\tau)}.\tag{11}
$$

DDR 与 Cache 是两个独立池，不能把带宽相加。官方事件在完成、插入、释放和 Pipe 队首条件满足时推进；同刻事件按核心、Pipe 和稳定序破同分，空闲时不主动加入可控等待。

精确目标是

$$
\min_X\bigl(F(X),Q^{\rm add}(X)\bigr)\quad\text{按字典序}.\tag{12}
$$

式（1）--（12）与官方递推共同定义离散优化问题；局部线性化不把整个模型变成标准 MILP。

### 5.4 困难性和必要下界

广义 B 模型至少弱 NP 难。给定 Partition 实例的正整数权重 $w_1,\ldots,w_m$，构造合法输入图：取 $K=2$，每个 $w_i$ 对应一个独立 M 操作，周期 $c_i=w_i$；操作之间无依赖、无 COPY 边，`validate_graph` 接受 `ops`、空 `tensors` 和空 `edges` 的这种合法输入编码。把所有操作分配到两个核心，Makespan 是两核负载最大值。令总和为 $W$，则存在 Makespan $\le W/2$ 当且仅当存在子集和为 $W/2$，即 Partition 的答案为 YES。输入使用二进制整数编码，$K=2$，周期为正整数，图是所定义模型的合法输入族。固定的 100 个比赛图不构成复杂度结论；这里不追加 3-Partition 的强 NP 难证明。

令 $W_q=\sum_{v:q_v=q}c_v$，$Q_{\min}=\sum_{T_{\rm in}}b_t+\sum_{T_{\rm prod}}o_tb_t$。统一 $K$ 核必要下界为

$$
LB_K=\max\left\{L_G,\frac{W_M}{K},\frac{W_V}{K},\frac{Q_{\min}}{60}\right\}.\tag{13}
$$

在空 Cache 且每个逻辑输入至少首次 miss 时，C 也要为 $Q_{\min}$ 提供 DDR 服务。对已评 C 计划可进一步使用

$$
F_C\ge\max\left\{L_G,\frac{W_M}{K},\frac{W_V}{K},
\frac{Q_D}{60},\frac{Q_L}{250}\right\},
$$

其中 $Q_D,Q_L$ 是事件中实际进入 DDR、Cache 池的字节服务量。由于 $LB_K\le F_K$，$T_1/LB_K$ 是由必要下界给出的乐观加速比上界；$T_1$ 未实测前不填。

## 6. 可执行的候选生成、轻量搜索与复杂度

### 6.1 静态状态、H/R 顺序和有界分支

预处理保存：操作邻接、反向消费者、每个张量的生产者、原始 COPY 端点、输入接收域、计算依赖弱连通分量、$W_M,W_V,L_G,Q_{\min}$、最大扇出、张量容量比例和反向关键路径

$$
 h(v)=c_v+\max_{v\to u}h(u),
$$

叶节点后继项为 0。H 序在就绪集合按 $(-h(v),v)$ 选取。

R 序只服务于容量导向起点，不让释放字节压过所有关键路径。默认从就绪集合取按 $(-h(v),v)$ 排序的前 $q=8$ 个操作，再在这最多 8 个操作中按

$$
(R_v-O_v,h(v),-v)
$$

降序选择；$R_v$ 是本操作后不再有计算消费者的输入字节，$O_v$ 是新产生且仍有后续读者的输出字节。释放量仅用于构造优先级，实际释放仍等待 `COPY_OUT` 等读者完成。去容量控制关闭 R，完全使用 H。

分量顺序按 $(-\max\{W_M,W_V\},\min v)$。分量装箱时逐个尝试目标核心，选择投放后全核最大 Pipe 负载最小者，再按新增输入接收域字节、核心号破同分。分量少于 K 时，额外块只能来自以下有界识别：

1. 找公共前段：反向从入度为零节点向下形成共同可达集合，直到第一个有多个可达支路的边界；
2. 找可并行支路：对每个候选边界计算支路操作集合，排除存在交叉依赖的支路；
3. 找汇合后段：识别多个支路重新进入同一后继集合的位置；
4. 只在边界前后保留连续块，块数上限为 $\min(n,4K)$（A/B 普通起点）或 $\min(n,8K)$（R 起点）。

公共输入被多个支路使用时，拆分前后重新计算每个张量的生产域、消费域、边界 COPY、100/1000 cycles 等待和容量扫描。A 不能因为“计算分量之间没有中间依赖”就省略共享原始输入的重复读取：输入在不同 Task 的接收域各计一次；只有同一 Task 内的消费者才去重。若分支边界不满足拓扑和商图检查，或增加的边界 COPY 与轻量代理不改善，退回未拆分块。B1 在分量过多时按上述分量顺序贪心分成 $g=\min(K,c)$ 个非空组；每次选择投放后最大 M/V 负载最小的组，增量输入接收域为第二比较量，核心号为第三比较量。组数超过 K 不再逐分量建块。

### 6.2 固定起点

| 起点 | 构造 | 块/核心上限 |
|---|---|---|
| A0 | 全图一个子图，放核 0；其余核为空 | 1 个非空 Task |
| A1 | 计算分量装箱，每个非空核合成一个 Task | 至多 K 个 Task |
| A2 | 分量连续序切成 $\min(n,2K)$ 块 | 按块拓扑序试放 |
| A3 | H 序切成 $\min(n,4K)$ 块 | 保留细粒度候选 |
| B0 | 全图一个子图，放核 0 | 1 个非空子图 |
| B1 | 分量按规则分成至多 K 组 | 每核一个合并 Task |
| B2 | H 序切成 $\min(n,4K)$ 块 | 预计完成时刻优先 |
| B3 | 有界 R 序切成 $\min(n,8K)$ 块 | 兼顾容量压力 |

切块时，剩余 $r$ 块的目标计算尺度为
$\max(M_r,V_r)/r$。在目标的 $[0.9,1.1]$ 倍窗口内优先选分量边界或跨切点依赖数局部极小的分支边界；若候选超过 64 个，按跨切点张量字节、负载偏差、位置截断。没有窗口内位置就选最接近者，最后一块吸收余项。该尺度只用于构造，不冒充真实执行时间。

B/C 轻量试放用块内 H 序递推计算 Pipe、输入到达和 500 cycles 同步；A 把块作为独立 Task，加入式（9）的 100/1000 cycles。轻量阶段不模拟共享带宽和真实 Spill，但完整 profile 会重建所有边界、Step2 和 Step3。

### 6.3 有界多轮局部改进

这是“受 FM 边界迁移思想启发的有界局部改进”，没有实现完整 FM 的增益维护、锁定、负增益路径或回退链。

按计算操作数固定规模档：

| 档位 | 条件 | 默认轻量轮数 $R$ | 每轮原始候选上限 A/B/C | 每个组合局部 profile 总上限 |
|---|---|---:|---:|---:|
| 小 | $n\le2000$ | 3 | 64/48/64 | 累计≤2（每轮最多提出 2） |
| 中 | $2000<n\le10000$ | 2 | 48/36/48 | 累计≤2（每轮最多提出 2） |
| 大 | $n>10000$ | 1 | 32/24/32 | 累计≤2（每轮最多提出 2） |

A 的原始候选优先顺序为：分量/分支边界切块和已有块移动；容量压力锚点；最后才是单操作新 Task。普通通道的单操作候选只有在操作属于跨域关联字节最大的前 32 个边界操作、会改变输入消费域或输出外域、并且轻量主字段严格改善时才保留；容量通道的单操作候选可凭独立压力锚点进入本轮容量 profile 名额，但只有 profile 后严格改善才更新 `current`。一次编辑至多新建一个单操作块，每轮至多 8 个此类候选，不因操作粒度小而固定枚举。A 的全部候选仍受总上限约束。

B/C 的编辑围绕生产者、末次消费者、共享输入和容量峰值：整块迁移、边界隔离、核内合法前移/后移各生成确定候选。一次编辑至多隔离两个操作，最多增加 4 个块；规范化后要求
$S\le\min(n,8K+16)$，超出即拒绝。C 另保留聚合、分散和错峰结构起点，最多四个新搜索 profile（见 §7.3）。

每轮流程固定为：

1. 从当前状态生成候选，按边界字节、关键路径、容量压力和操作 ID排序；
2. 依次检查覆盖、唯一性、商图、适用的核序约束和块数；
3. 更新所有受影响张量的生产域、消费域、边界 COPY、核序和轻量时间；不能只更新触发编辑的共享输入；
4. 用数值代理字段严格比较当前状态。只有第一字段或前序数值字段严格改善才接受；完全相等不接受，`plan_key` 只用于已接受集合的并列保留；
5. 接受后立即成为下一轮状态，候选集合和旧锚点失效；规范化 `plan_key` 去重；
6. 达到轮数、没有严格改善、候选耗尽、块数/内存上限或 profile 名额耗尽时停止。未用完名额不转给其他图。

普通 A/B 候选的轻量评分先于完整 profile 计算。令 $H_{A/B}^{\rm light}$ 为加入计算依赖、Pipe 相邻边、核序和适用的 A 激活等待后的参考最长路，$W_{k,q}^{\rm light}$ 为核心 $k$ 上计算 Pipe $q\in\{M,V\}$ 的周期工作量，$Q^0$ 为式（5）或式（6）的基础结构搬运量，则

$$
J_{A/B}^{\rm light}=\max\left\{H_{A/B}^{\rm light},
\max_{k,q}W_{k,q}^{\rm light},\frac{Q^0}{60}\right\},
\qquad
\operatorname{score}_{A/B}^{\rm light}=
\left(J_{A/B}^{\rm light},Q^0,\operatorname{plan\_key}\right).
$$

普通通道只有在去掉 `plan_key` 后的数值元组严格改善时才更新 `current`；`plan_key` 只在数值完全相同时破同分，不把它当作改善证据。容量压力量由同一官方序的无换出理想活跃扫描得到：

$$
P^{\rm peak}(X)=\sum_{k,m}\left[\max_j\widehat M_{k,m}(j)-C_m\right]_+.
$$

容量通道单独排序，不与普通元组合并：先按压力锚点的目标 Spill 恢复字节降序；没有真实 Spill 时按 $P^{\rm peak}$ 降序；再按理想峰值下降量降序和 `plan_key` 升序。每轮保留至多一个普通候选和一个容量候选进入 profile；容量候选即使普通元组未改善，也可占用这一独立名额，但只有 profile 后数值严格改善时才成为下一轮 `current`。跨全部轮次最多两个局部 profile，未入围候选只做轻量回放。

容量候选必须注明来源：它来自当前状态的官方 Spill 记录，或来自同一官方序的理想活跃峰值；不把理想超额写成真实 Spill。局部 profile 之后仍按 §6.4 的第二槽资格规则决定是否进入官方评估。

结构候选的可数上限也固定。A 的一轮原始枚举至多为 128 个边界迁核计划、16 个有因果触发的单操作新 Task、32 个整块迁移、8 个边界拆分和 8 个相邻合并，共 192 个；没有满足触发条件的单操作候选时为 176 个。B 至多为 128 个操作迁核、16 个合法顺序移动和 16 个容量候选，共 160 个。C 除 B 的 160 个候选和 16 个错峰候选外，聚合/分散结构起点各最多 8 次内部迁移或切段试放，因此每个 C 组合最多还有 16 次结构轻量评分；合并计为最多 192 个轻量候选。规模档表中的 64/48/32 等数字是更严格的实际截断值，先按结构优先级取前 $q$ 个，再做轻量检查。每一个被枚举的计划都计一次商图/核序检查、域更新、轻量回放和去重；不因最后没有进入 profile 而记为零成本。

### 6.4 A/B profile、第二位置和失败处理

profile 采用一次官方构图入口和整计划缓存，键为原图、场景、K、规范化计划、配置和官方版本。缓存保存 Step1 序、Step2 Spill/Reload、Step3 Pipe/内存依赖、边界逻辑身份和节点/边数。不同计划默认不复用域级局部计算，避免生成 ID、稳定分桶或边界归属不一致。

A/B 的参考代理从扩展图构造参考 DAG。它合并计算依赖、内存依赖、Pipe 相邻边和 A 的 Task 激活约束；B/C 对跨核 COPY 加 500 cycles。令 $H^0_{A/B}$ 为该参考图最长路，$W_D^0$ 为基础 DDR 独占工作周期，定义

$$
J_{A/B}=\max\{H^0_{A/B},W_D^0\},\qquad
\operatorname{score}_{A/B}=(J_{A/B},Q^{\rm sched},Q^{\rm spill},\operatorname{plan\_key}).\tag{14}
$$

$W_D^0$ 已由逐 Pipe 路径体现时不重复相加。该代理忽略动态共享带宽传播，官方结果才是正式值。

令 $S$ 为规范化、profile 成功且适用空核热启动已加入的初始集合。按原有完整代理元组取

$$
X_0=\arg\min_{X\in S}\operatorname{score}(X).
$$

令 $L$ 为多轮局改产生且 profile 成功的候选。定义

- $S_{\rm alt}$：S 中与 X0 的规范化 $g,a,\sigma$ 至少一项不同、且本组合尚未正式比较的候选；
- $L_+$：普通局部 profile 中与 X0 不同且不含 `plan_key` 的完整数值代理元组严格优于 X0 的候选；
- $L_{\rm cap}$：至多一个容量通道 profile，在完整数值代理上严格优于 X0 的候选。它可以来自轻量普通元组未改善的容量候选，但必须先通过完整 profile 的数值比较。

第二位置固定从去重后的 $S_{\rm alt}\cup L_+\cup L_{\rm cap}$ 中按同一代理元组取最小者 $Y$。因此有严格改善的普通局部候选时优先比较它；容量候选只有经过完整 profile 且数值严格改善后才进入同一池；没有局部改善时，已完成 profile 的另一种初始结构仍有机会进入第二位置。池为空才不安排第二位置。第一槽失败不释放第三个位置；若 Y 已预先确定，仍可评 Y。全部初始 profile 失败时，跳过局改，第一槽使用 A0/B0 或已保存的补空计划；失败也占槽。

这条规则是 A/B 的统一默认协议。C 不把所有 B 起点机械套入同一规则，而按 §7.3 固定 XB 加至多一个 C 挑战。

### 6.5 复杂度、数据结构和伪代码

令 $t$ 为张量数，$I$ 为操作--张量关联数，$S$ 为当前子图数。邻接、域计数和静态路径为 $O(n+t+I)$；堆式 H/R 更新为 $O((n+I)\log n)$。每轮原始候选生成和轻量回放上限已按规模档固定，每个候选的合法性、域差量、核序和轻量时间为 $O(n+t+I+S^2)$；局部 profile 还包含官方构图、Step1--3、参考 DAG 和容量扫描，记为 $P_r(G,X)$，不能用“差量更新”称为常数时间。C 的 FIFO 代理按查询事件排序，另有 $O(N_{\rm in}\log N_{\rm in})$。

```text
solve_AB_family(G, scene, K_request, mode, fixed_budget):
    build static graph, domains, components, H/R and scale bin once
    if mode == V1:
        previous_v1 = NONE
        for k in the fixed prefix up to K_request:
            S = prescribed seeds for k plus eligible padded previous_v1
            profile distinct valid seeds; choose X0 by the fixed proxy tuple
            evaluate X0 in the first official slot
            if X0 fails: use the explicit A0/B0 or padded fallback in that same slot
            save V1[G, scene, k] = {
                initial_candidates: S,
                first_slot_plan: X0_or_fallback,
                first_slot_result: result,
                prepared_state: matching_state,
                v1_winner_for_next_k: successful_result_or_NONE
            }
            previous_v1 = V1[G, scene, k].v1_winner_for_next_k
        return all V1 states and cost records

    if mode == V2:
        for k in the fixed prefix up to K_request:
            state = read_only(V1[G, scene, k])
            S = state.initial_candidates
            X0 = state.first_slot_plan
            first_result = state.first_slot_result
            current = X0
            for round in 1..R(scale):
                generate bounded ordinary/capacity edits from current
                legal-check and light-replay every candidate
                accept ordinary edits only on strict score_A/B_light improvement
                update domains/order/time; keep capacity candidates in their separate slot
                deduplicate plan_key; across all rounds keep at most two profile candidates
            L = successful local profiles
            L_cap = at most one capacity profile with strict full-proxy improvement
            Y = select_second_candidate(S_alt union L_plus union L_cap) by §6.4
            if Y exists: evaluate Y in the second official slot
            retain min(first_result, second_result) by exact (F, Q_add)
            write V2[G, scene, k] only; never update V1 or a V2 previous-winner chain
        return V2 results and cost records

solve_C(G, K, mode, config):
    if mode == V1:
        run or reuse the fixed B V1 prefix through K; save C_V1[G, K] with XB and its prepared state
        score and evaluate fixed XB in the first official slot
        return and preserve C_V1[G, K]
    if mode == V2:
        state = read_only(C_V1[G, K])
        XB = state.XB; first_result = state.first_result
        score bounded aggregate/disperse/offset candidates with the two-pool proxy
        evaluate at most one qualified C challenger in the second official slot
        do not replace XB or write a new B history
        return min(first_result, challenger_result) by exact (F, Q_add)
```

## 7. A、B、C 的递进求解

### 7.1 A：Task 粒度、输入消费域和 100/1000 cycles

A 的一个子图就是一个 Task，切开一个图会同时改变三件事：输入可能在更多 Task 中接收，计算结果可能产生更多外域写出，同核 Task 之间新增至少 100 cycles；跨核前驱还要等待 1000 cycles。因此 A 的拆块只在分量/分支边界、已有块移动或明确容量压力处优先。每次拆分都重新计算 $I_A(t)$、$R_A(t)$、$Q_A^0$、Task 前驱和容量状态。

A1 适合独立分量数接近 K 的图；A2/A3 用有限块提供更细并行度。对公共根 fork--join 图，前缀分量数可能始终为 1，算法改为识别公共前段和支路边界；没有合法边界就不强行拆。普通通道的单操作新 Task 需要 §6.3 的跨域/关键路径触发和轻量严格改善；容量通道可由独立压力锚点保留一个 profile 名额，只有完整 profile 严格改善才进入第二槽，并受每轮 8 个、总候选上限约束。

### 7.2 B：核心驻留域、核序和容量

B 把同核子图合并成一个 Task，同核数据可以驻留复用，但 L1/UB 仍是硬容量。B1 将计算分量分到不超过 K 个组；B2 用 H 序分成最多 4K 块；B3 用前 8 个高 H 就绪操作中的 R 规则提供容量导向起点。核内子图列表影响稳定分桶，官方 Step1 仍决定最终局部顺序，Step2 仍决定 Spill/Reload。

容量通道从 profile 的实际 Spill 恢复字节降序选前 8 条；尚无 Spill 时从同一官方序的理想活跃峰值选锚点。候选尝试提前末次消费者或延后大输出生产，并重新运行完整容量扫描。R 只作为独立容量起点，默认 ready 集合先受 H 前 8 限制，避免大量释放字节操作遮蔽关键路径。

### 7.3 C：两池评分、聚合/分散起点和 FIFO 反馈

C 对每个组合冻结当前 K 的 V1 B 赢家 $X_B^{\rm V1}$，在同一提交结构上跑只读 FIFO Cache；V2 不替换成另一条 B 热启动链。缓存键、可缓存对象和插入/淘汰语义直接沿用 `multicore_cut_evaluate_problem_3.py`：只有 `COPY_IN` 查询逻辑张量 id；命中走 Cache 池且不刷新 FIFO；miss 走 DDR，完成后按先进先出插入；大于容量的对象不插入。

对图输入 $t$，接收核心数为 $r$，$B_D=60$，$B_L=250$，Cache 容量为 $C_L$。轻量层保留首读 DDR、后读 Cache 的乐观假设，但分别统计两个资源池：

$$
(d_t^{\rm light},\ell_t^{\rm light})=
\begin{cases}
(0,0),&r=0,\\
\left(b_t/B_D,(r-1)b_t/B_L\right),&r\ge1,\ 0<b_t\le C_L,\\
\left(rb_t/B_D,0\right),&\text{其他情形}.
\end{cases}\tag{15}
$$

$O_D$ 为不含图输入的其他基础边界 COPY 的 DDR 独占周期总和，包括每个远端接收核的中间张量写/读和独立最终输出；每条 COPY 采用 `max(1, ceil(bytes/60))`。定义

$$
W_D^{\rm light}=\sum_{t\in T_{\rm in}}d_t^{\rm light}+O_D,
\qquad W_L^{\rm light}=\sum_{t\in T_{\rm in}}\ell_t^{\rm light}.
$$

保持依赖、核序与 500 cycles 的轻量回放，令 $L_{\rm light,C}$ 为参考路径，主分数为

$$
J_{\rm light,C}=\max\{L_{\rm light,C},\max_{k,q}W_{k,q},W_D^{\rm light},W_L^{\rm light}\},
$$

$$
\operatorname{score}_{\rm light,C}=
\left(J_{\rm light,C},W_D^{\rm light}+W_L^{\rm light},\operatorname{plan\_key}\right).\tag{16}
$$

两池合计只作次级字段，不能把 Cache 工作和 DDR 工作串成一个主时间项。候选 `(1200,1000,300)` 与 `(1100,1000,500)` 的旧合计主分数分别为 1300 与 1500，而新主分数为 1200 与 1100；这是说明性资源评分，不是官方用例时间。

C 的结构起点从冻结 $X_B$ 出发：

- **聚合**：按“输入字节×消费块数”降序选最多 8 个共享输入，把其消费块逐个试迁到已有消费者计算量最大的核；每次迁移都重算所有受影响输入、输出和容量域，只有完整两池分数严格改善才保留。
- **分散**：重新找到该输入的去重消费块，在 H 序窗口中把一个较重连续段试放到其他核；没有两个非空段、新接收核或合法商图边界就跳过，不补无因果拆分。
- **错峰局改**：对重复可缓存 miss，最多取前 8 个逻辑张量，只有确实改变 MTE2 顺序或依赖，才生成 leader/follower 重排候选。只移动独立计算位置而未改变 Cache 插入与淘汰关系的候选不计入收益。

完整 C profile 对每个 `COPY_IN` 建立查询/完成事件，完成先于同刻查询，按核心、Pipe 和稳定次序破同分；固定第一遍查询/完成流后回放 FIFO，得到预计命中集合，再以 Cache 带宽重算一次参考最长路。令 $W_D(\hat h)$、$W_L(\hat h)$ 分别为实际进入两个池的独占周期，$\hat H$ 为预计命中字节，$\hat M$ 为 miss 的 COPY_IN 字节，$\hat D=\hat M+$ DDR 写出字节。正式 C 代理为

$$
J_C=\max\{H^{(1)},W_D(\hat h^{(0)}),W_L(\hat h^{(0)})\},
$$

$$
\operatorname{score}_C=\left(J_C,\hat D/60,-\hat H,Q^{\rm spill},\operatorname{plan\_key}\right).\tag{17}
$$

完整 profile 和最终评估仍按逐 COPY 取整、真实 FIFO 事件和动态共享带宽执行。C 的候选沿用 §6.3--§6.4 的严格数值改善、两槽和失败占位规则；本节只规定两池与 FIFO 事件的代理字段。最终已评方案按精确 $(F,Q^{\rm add})$，不按代理排序替换真实结果。

### 7.4 Pareto、控制与零容量口径

每个组合最多得到第一槽和第二槽两个真实点，主答案写成有限候选比较，不把它描述成丰富 Pareto 前沿。若需要展示同一结果集的搬运折中，唯一默认值为 $\varepsilon=0.01$：在该组合已评集合中取 $F\le1.01F_{\min}$ 的点，再选 $Q^{\rm add}$ 最小者；$\varepsilon$ 的单位是相对 Makespan，不能与代理严格改善或真实评估容忍混用。主结果仍是精确字典序最小。

正式无 L2 口径沿用问题 2 的 B；C 的默认配置为 `read_only`。后续第一步在完全相同输入、XB、K、L1/UB、DDR 和其余配置下比较 C 容量 0 与 B 入口 Makespan：相等时只报告已测范围和语义依据；不等时定位 Cache 配置、COPY 路径或其他代码差异，不强行合并口径。容量 0 只用于代表设置的配对核对，不扩展成全量零容量基线。

## 8. 说明性手算

以下数值只说明公式，不能替代官方评估。

### 8.1 同一张量在 A/B 中的收费不同

设图输入 $x$ 为 60000 bytes，被两个计算域使用；中间结果 $z$ 为 30000 bytes，两个域都需要；最终输出为 4 个 6000 bytes。若 A 中两个消费者分属两个 Task，则 $x$ 按两个接收域计，$z$ 产生一次源写并对外域计写出；若 B 中两个消费者位于同一核心，$x$ 只保留一个接收核域，$z$ 的远端对数也减少。把操作从核 0 移到核 1 后，B 的 $I_B$ 和 $R_B$ 必须重新计算，不能只减去一个“通信边”。同核驻留不等于零成本，容量不足时仍会产生 Spill。

### 8.2 Task 等待可能抵消并行

链 $a\to t\to b$ 中，$a,b$ 的计算分别为 1000、800 cycles，$t$ 只作依赖示意。若把三者放入一个 Task，忽略边界搬运的计算路径为 1800。若按 A 的真实 Task 激活语义把链切成同核两个 Task，第二 Task 至少等待前一 Task 完成后的 100 cycles，路径为 $1000+100+800=1900$，并且两个 Task 各自的边界 COPY 仍要按张量字节计入；若切到不同核心，跨核前驱至少增加 1000 cycles，计算路径为 $1000+1000+800=2800$，再加源写/目标读的 COPY 时间。V0.5 的 2300/3200 是另一组逐项参数：它把中间 $t$ 的 200 cycles 和两段各 200 cycles 的边界 COPY 写进路径，即 $1000+200+100+200+800$ 与 $1000+200+1000+200+800$；本例把 $t$ 仅作依赖示意，并把边界 COPY 作为另计搬运，所以不能把两组数混用。两个互不相依、各约 1800 cycles 的分支放在两核可并行，放在一核则约 3600。结论取决于依赖与搬运，不由“块越细越好”决定。

### 8.3 容量候选不能把理想峰值当 Spill

若某核在旧序申请两个 81920 bytes 输出，UB 容量为 131072，理想峰值为 163840，超额 32768。调整顺序后若两个输出不重叠，理想峰值可降为 81920。实际 Step2 是否写回 32768、81920 或完整张量，取决于官方物理版本、`next_use` 和 DDR backing；轻量峰值只用于产生容量候选，最终 profile 读取真实 Spill 记录。

### 8.4 C 的两个资源池

假设同一输入大小为 60000 bytes，被两个核心读取，Cache 容量可容纳它。第一次读占 DDR 约 $60000/60=1000$ cycles，第二次命中占 Cache 约 $60000/250=240$ cycles。若第一读完成并插入后第二读才查询，第二次可能从 $1000$ 时刻开始，完成约为 1240；若两次查询同时发生，第二次仍是 miss。改变排序只有在确实改变 MTE2 查询、完成和 FIFO 插入/淘汰关系时才有 Cache 依据。容量 100000 bytes 时再插入 50000 bytes 的 $y$ 会淘汰先入的 $x$；命中不会刷新 $x$ 的 FIFO 位置。

## 9. 后续验证、完整实验、8 小时预算与四天安排

### 9.1 最小验证顺序

后续第一步按以下顺序完成，当前阶段不执行：

1. 手写方案做 A/B 的 K-1 补空核检查，以及 A0/B0 与统一单核 $T_1$ 的核 0 保底检查；检查提交合法性、商图、Task/核心顺序和 Makespan 是否等价。C 不从这两项推导等价性。
2. 对最小、中位、最大图启动官方入口计时，覆盖构图、轻量候选、profile、模拟、Cache 回放和 I/O。选图规则是按计算操作数排序后的首个、最接近中位数且 ID 最小者、末个；若并列取 case ID 最小。每个图测统一 $T_1$、A 的 K=2/5、B/C 的 K=1/5，共 21 个观测（每图 7 项），使用合法固定计划。计时计划不是另行挑选：先按 V1 的固定起点、代理元组和规范化 `plan_key` 确定并冻结每个首槽计划，V1 随后必须复用相同键；统一 $T_1$ 也冻结其单核计划。其中 18 个 A/B/C 观测附着在 V1 首槽，3 个 $T_1$ 观测附着在统一单核覆盖；若未来必须更换计划键，先冻结新协议并重新核算官方上限，不沿用 3590 的旧算术。
3. 记录冷启动与批量摊销：单独请求 C 的 K=5 时包含 B 的 K=1--5 前缀构造、profile、官方评估、prepared 状态保存、C profile 和评估；只有完全相同图、场景、K、配置和计划才复用。三个选定图各做一组额外的 C、K=5 冷启动与已准备状态复测，共 6 个专门计时槽，用来拆分进程冷启动、B 前缀摊销和 C 评估成本；它们不替代前一条的 21 个附着观测。不能把 C 的单例约 5--10 分钟建议隐藏在 B 的批量时间里。

最小机制微图合并为 12 个名额：A 空核/单核两张、B 空核/单核两张、有限块隔离两张、容量调序两张、C 迁移两张、C 错峰两张。它们是手写计划和边界事件检查，不增加新的全量矩阵。微图只能证明对应实例。

冷启动 C 的单例成本单独记为

$$
T_{C,\mathrm{cold}}(G,5)=
\sum_{k=1}^{5}\bigl(t_{B,\mathrm{static/light},k}+t_{B,\mathrm{profile},k}+t_{B,\mathrm{eval},k}+t_{B,\mathrm{io},k}\bigr)
 +t_{C,\mathrm{static/light}}+t_{C,\mathrm{profile}}+t_{C,\mathrm{eval}}+t_{C,\mathrm{io}}+t_{\mathrm{cold}}.
$$

这里 `static/light` 包含 B 前缀的候选构造、商图/执行合法性、轻量回放和去重；`t_C,eval` 已包含官方 C 的 Cache 事件，不能再把同一事件模拟重复加入 `t_C,profile`。

批量运行只有在图、场景、K、规范化计划、配置和官方版本完全匹配时扣除已保存的 B prepared 状态；单例若没有该状态，必须把 B 前缀和 C 全部成本记入。题面约 5--10 分钟只是效率建议，不是本轮测得的单例时间。

每次计时记录：图 ID、n/t/I、场景、K、计划键、配置版本、进程/导入冷启动秒数、首次构图秒数、轻量回放秒数、profile 秒数、完整模拟秒数、Cache 回放秒数、I/O 秒数、峰值 RSS、失败类别和是否复用。首次开销、可复用开销、冷启动单例和批量摊销分开记录。

### 9.2 正式覆盖和控制

主矩阵为 100 个输入：统一单核一次；A 覆盖 K=2--5；B 覆盖 K=1--5；C 覆盖 K=1--5 的 B 计划、同计划 Cache 和至多一个 C 挑战。六个代表图按三组规模（小/中/大）与 DDR/计算比的低、高端点选取，沿用 `case_078、case_012、case_073、case_081、case_016、case_084`，代表对照只报告 K=2、5。

每个 A/B 正式组合保存第一槽与最终槽：第一槽 Makespan、最终 Makespan、真实增益、第二槽胜率、两槽均失败次数和新增 profile/官方耗时。V1 本身就是固定起点、无局部改进的基线；局部收益指在相同 V1 初始化与热启动历史下的变化。若要比较另一条独立热启动链，才另计诊断，不能用局部收益字段代替。

控制只做三类：去显式接收域引导（A/B）、去容量引导（B，R 改为 H）和轻量代理 A。每个控制使用自己的起点、前缀和第二位置，不把主方法赢家注入控制。报告六代表、K=2/5 的配对差异、分布、失败和耗时；新增分支起点只在替换原起点时计费，不扩展全量矩阵。

轻量代理 A 控制只在代表图运行。对每个控制候选，用基础边界 COPY、官方 Step1 序、计算依赖、逐 Pipe 次序和 A 的 Task 激活关系构成未做 Step2/3 的参考图，最长路记为 $H_A^0$，基础 DDR COPY 独占工作量为 $W_D^0$。沿各 Task 的 Step1 序做无换出理想存活扫描：输入在搬入输出申请时出现，计算输出在申请时出现，最后一次使用包括边界 `COPY_OUT`；当前位置先申请输出，再释放已完成末次使用的输入。令

$$
P_A^0=\sum_{s,m}\left[\max_j\widehat M^0_{s,m}(j)-C_m\right]_+,
$$

其中 $\widehat M^0_{s,m}(j)$ 是 Task $s$ 在位置 $j$、存储类型 $m$ 的理想活跃字节。该控制固定使用

$$
J_A^{\rm light}=\max\{H_A^0,W_D^0\}+P_A^0/60,
\qquad
\operatorname{score}_A^{\rm light}=
\left(J_A^{\rm light},Q_A^0,P_A^0,\operatorname{plan\_key}\right).
$$

$P_A^0/60$ 是固定容量压力评分，不是实际 Spill 时间；第一字段可用整数 $60\max\{H_A^0,W_D^0\}+P_A^0$ 比较，避免浮点持平误判。容量锚点来自该控制自己的 Step1 理想峰值，仍保留一个容量候选名额，不额外运行 Step2/3 取得真实 Spill。其初始选择、局部候选排序和第二位置沿用 §6.3--§6.4，但使用本控制自己的评分和热启动结果；最终官方评估仍执行完整步骤并记录真实指标。

### 9.3 调用和 profile 上限

失败调用占用名额，精确相同计划和配置可复用；复用必须记录命中条件。新规则让 A/B 的第二位置更容易被使用，但仍没有第三槽，因此最坏正式调用上限保持并重新由槽数推导如下：

| 项目 | 组合数与每组合上限 | 最坏官方调用 |
|---|---|---:|
| 统一单核 | 100×1 | 100 |
| A 主协议 | 100×4 个 K×2 槽 | 800 |
| B 主协议 | 100×5 个 K×2 槽 | 1000 |
| C 固定 XB | 100×5 | 500 |
| C 条件挑战 | 100×5×1 | 500 |
| 主矩阵小计 | 以上合计 | 2900 |
| 去接收域控制 | 6×(4+5)×2 | 108 |
| 去容量控制 | 6×5×2 | 60 |
| 轻量代理 A 控制 | 6×4×2 | 48 |
| 三类控制小计 |  | 216 |
| C 非默认参数 | 10 配置×6 图×2 K×2 槽 | 240 |
| C 最终计划的 B 诊断 | 6×2 | 12 |
| 切窗控制 | 6 图×4 A 前缀×2 新容忍度×2 槽 | 96 |
| 代理/候选诊断 | 36 组×3 未评计划 | 108 |
| 12 个机制微图 | 6 对×2 | 12 |
| 最小/中位/最大计时复测 | 3 个选定图各 1 个 C、K=5 冷启动槽 + 1 个已准备状态复测槽（另有 21 个观测附着于 V1/统一单核） | 6 |
| **完整官方调用上限** | $2900+216+240+12+96+108+12+6$ | **3590** |

V1/V2 在主矩阵中的分解是：V1 第一槽最多 $100+400+500+500=1500$ 次；V2 复用 V1 第一槽，第二槽最多 $400+500+500=1400$ 次。控制和诊断另计。严格独立 V1/V2 热链不在 3590 内，需另加每个输入条件下的首槽成本。

profile、轻量回放和官方调用分开计数：

| 类别 | V0.6 默认上限 | 计算口径 |
|---|---:|---|
| A/B 主矩阵 profile | $100(27+34)=6100$ | A：V1 起点 $4+3\times5=19$，V2 局部最多 $4\times2=8$；B：V1 起点 $4+4\times5=24$，V2 局部最多 $5\times2=10$ |
| C 主矩阵 profile | $500\times4=2000$ | V1 固定 XB 1 个；V2 聚合/分散/错峰状态共至多 3 个，合计每组合 4 个 |
| 主矩阵 profile 小计 | 8100 | 与 2900 次官方展开独立 |
| 去接收域控制 | 366 | 6 图的 A/B 前缀按原起点上限重建 |
| 去容量控制 | 204 | 6 图 B 前缀重建 |
| 非默认 C 配置 | 480 | 只对新配置重放，不重跑可精确复用的 XB |
| 切窗控制 | 324 | 6 图、A 前缀、两新增容忍度 |
| 保真度/候选诊断 | 144 | 只对缺少可复用 prepared 状态的计划重建 |
| **完整 profile 上限** | **9618** | $8100+366+204+480+324+144$ |

轻量代理 A 控制另有最多 162 次 Step1 序和理想活跃扫描。对每个图、场景和 K，轻量工作量按

$$
N_{L}=N_{\rm seed}+\sum_{r=1}^{R}N_{\rm raw}(r)+N_{\rm C,struct}+N_{\rm control}
$$

核算：对 A/B，$N_{\rm seed}=4+\mathbf 1\{K>K_{\min}^{\rm scene}\land X_{K-1}^{\rm pad}\text{ 可用}\}$，其中 $K_{\min}^{\rm scene}$ 是该 family 的首个请求核数（A 为 2，B 为 1）；首个核数没有上一核可用补空计划时只计 4 个规定起点。$N_{\rm raw}(r)$ 取规模档的 A/B/C 截断值，$N_{\rm C,struct}\le16$ 是 C 聚合/分散/错峰结构的内部试放；C 的 V1 固定 $X_B$ 默认直接读取 B 的已保存轻量分数和 prepared 状态，不新增 light。若 C 冷启动或状态缺失而必须重算固定 $X_B$，该次计入 $N_{\rm C,struct}$，并把结构试放上限收紧为剩余至多 15 次。$N_{\rm control}$ 是控制方法新增候选。每个 $N_L$ 计商图/核序检查、域更新、轻量回放、去重和排序；不能因 profile 上限不变而把总耗时写成不变。A/B 起点、V1 第一槽与 V2 第二槽的 profile 只在同场景、同 K、同计划和同配置时复用；C 冷启动不免费继承 B 的构造。

### 9.4 8 小时工时公式和规模档

目标设备为 MacBook Pro M4 Pro、48GB 统一内存。后续累计实验墙钟目标为 8 小时，即 28800 s。令批次 $b$ 的互斥工作量为

$$
W_b=\sum_j(t_{\rm static,j}+t_{\rm light,j}+t_{\rm profile,j}+
 t_{\rm eval,j}+t_{\rm cache,j}+t_{\rm io,j}),
$$

其中 `static` 每图只算一次，`light` 按候选和轮次计，`profile` 按上表计，`eval` 按官方调用计。设阶段共享基线 RSS 为 $M_0$、每个 worker 的最大增量为 $m_b$、预留内存为 $M_{\rm res}$、硬件可用 worker 上限为 $p_{\rm hw}$，则

$$
p_{\rm eff,b}=\min\left\{p_{\rm hw},
\left\lfloor\frac{48\,\mathrm{GiB}-M_0-M_{\rm res}}{m_b}\right\rfloor\right\}.
$$

$M_0,m_b,M_{\rm res}$ 是待首轮计时取得的设计字段；若 $p_{\rm eff,b}<1$，该批次改为串行或先减少保留状态。有效并发为 $p_{\rm eff,b}$，则

$$
 T_{\rm wall}\approx T_{\rm prepare}+
\max\left\{\sum_bW_b/p_{\rm eff,b},T_{\rm critical}\right\}+T_{\rm summary},
\quad
T_{\rm wall}\ge\max_b T_{\rm longest,b}.\tag{18}
$$

预留 3600 s 给环境准备、结果汇总和返工，工作阶段为 25200 s。阶段设计配额固定为：V1 全量不超过 10800 s，V2 局部改进不超过 9000 s，控制/参数/微图不超过 5400 s；这些是未实测阈值。每阶段必须同时满足
$T_s=T_{\rm serial,s}+W_s/p_{\rm eff,s}\le B_s$、$T_{\rm critical,s}\le B_s$，并且顺序执行的阶段满足 $\sum_s\left(T_{\rm serial,s}+W_s/p_{\rm eff,s}\right)\le25200$。若把 3590 次完整调用及其伴随工作平均摊开，达到目标所需吞吐为

$$
\bar t_{\rm work}\le\frac{25200p_{\rm eff}}{3590}
=7.0195p_{\rm eff}\;\text{s/官方调用}.
$$

$p_{\rm eff}=2$、4 时分别为 14.04、28.08 s。该式只是设计阈值，未取得实测前不写成预算已验证。并发按小/中/大图的真实 RSS 决定，不填满 48GB；冷启动 C 的 B 前缀和 C 评估属于同一关键链，不能与独立图无限并行。

规模档固定搜索机会，不随实时负载变化：小图 $R=3$、每轮 A/B/C 原始候选 64/48/64；中图 $R=2$、48/36/48；大图 $R=1$、32/24/32。若计时显示 8 小时不可达，优先减少重复 profile、候选诊断和低价值参数格，不删统一单核、100 图 V1 覆盖或核心机制对照；修改档位后冻结新协议并重新计算上限。

### 9.5 四天实施安排

| 天数 | 交付 | 先后依赖 |
|---|---|---|
| 第一天 | 空核/单核等价手写检查；最小、中位、最大图官方入口计时；记录冷启动 C 前缀 | 先取得合法方案和耗时证据，再冻结并发和规模档 |
| 第二天 | 实现固定起点、profile 缓存和统一单核；完成 V1 的 A/B/C 全量第一槽 | V1 结果先落盘，不能把 V2 预跑隐藏在表外 |
| 第三天 | 运行 V2 多轮局部改进、A/B 第二槽、C FIFO 挑战；完成第一槽/最终槽配对 | 只复用同计划 prepared；不同热链另计 |
| 第四天 | 12 个机制微图、三类控制、零容量配对、参数点、代理保真度、耗时汇总与写作 | 先冻结结果字段，再整理图表和论文主线 |

## 10. 论文主线、图表与方法介绍

论文用“驻留域约束下的多核划分与只读 Cache 调度”作为工作名称，按题意分析、统一模型、A、B、C、实验和模型评价展开。

核心图表包括：三场景执行机制图；100 图的规模、分量和 DDR/计算分层；逐用例 Makespan 与 $Q^{\rm add}$；第一槽到最终槽的配对差异；真实 Spill 与容量候选；C 的 DDR/Cache 服务字节及 FIFO 事件；三类控制的配对差异；固定 XB 与 C 适配方案的硬件/算法分解；容量 0 对照；小/中/大图耗时和 RSS。每张图说明单位、样本范围和结果状态。有限候选只画已评点，不插值出未测 Pareto 曲线。

平均加速比使用统一单核口径

$$
\overline S_K=\frac1{100}\sum_{i=1}^{100}\frac{T_{1,i}}{F_{i,K}}.
$$

若某些用例失败，报告成功覆盖率和失败类别，不填零、不悄悄改变分母。多核加速比超过 K 可能来自单核固定启发式次序与多核方案不同，回到计划和事件记录解释；不把异常曲线归因于代码错误，也不自动宣称超线性收益。

可直接用于正文的方法介绍：

> 我们把一份张量可以在片上连续复用的操作范围定义为驻留域。问题 1 把子图作为 Task，问题 2 把同核子图合并为核心 Task，问题 3 在此基础上回放只读 FIFO Cache 的查询、完成和插入事件。求解器先从计算依赖分量、公共支路和关键路径构造有限起点，再以每个张量的生产域、消费域和容量压力计算轻量代理。多轮局部改进只接受严格改善的合法编辑，接受后立即更新域计数、核序和轻量时间；最终少量 profile 经过官方 Step1--3 和事件模拟，以真实 Makespan 与新增搬运量确定结果。这样，计算负载、同步、片上容量和重复输入读取在同一提交接口上被逐步比较。

论文必须区分：静态下界、轻量代理、官方 profile、官方完整结果；设计值、实测值、失败和未测项各用自己的状态。不要把程序运行成功、有限候选最好、必要下界或缓存命中率直接写成全局最优、科学收益或正式提交状态。

## 11. 拟建代码接口、输入输出、依赖和实现顺序

下面均为拟建接口；官方代码只作为只读依赖。

| 模块 | 输入/输出 | 责任 |
|---|---|---|
| `parse_graph` / `static_features` | JSON → 邻接、分量、路径、域和规模档 | 一次静态预处理 |
| `canonical_plan` / `validate_plan` | $g,a,\sigma$ → 两个提交字段、规范化键、覆盖与商图检查 | 不生成 COPY |
| `tensor_domain_delta` / `rollback` | 编辑 → 生产域、消费域、$Q^0$ 差量和撤回日志 | 覆盖整块和共享输入 |
| `build_seeds` / `list_schedule` | 图、场景、K → A0--A3/B0--B3 和 C 起点 | 固定顺序和块数上限 |
| `light_replay` | 候选 → 代理路径、Pipe 负载、DDR/Cache 两池量 | 每轮每候选执行 |
| `build_task_profile` / `build_core_profile` | 规范化计划 → 官方 Step1--3 prepared 状态 | 保存 Spill、Pipe、内存依赖 |
| `replay_fifo` | prepared、Cache 配置 → 查询、命中、插入和淘汰代理 | 不改变官方事件语义 |
| `propose_edits` / `refine_rounds` | 当前状态 → 多轮合法严格改善状态 | 不实现完整 FM |
| `solve_v1` | 100 图、A/B/C、固定起点 → 第一槽结果 | 全量早交覆盖 |
| `solve_v2` | V1 状态 → 局部 profile、第二槽和最终结果 | 复用同计划 prepared |
| `evaluate_saved_plan` | 官方输入+计划+config → Makespan、搬运、Cache 字段 | 失败原样记录 |
| `summarize` | 结果记录 → 第一槽/最终槽、控制、耗时和图表表格 | 不填未测数字 |

实现顺序为：先完成提交字段与静态特征；再实现空核/单核手写计划和计时；接入官方 profile 与直接评估，完成 V1；然后加入域差量、多轮轻量和 V2；最后接入 C 的 FIFO 代理、容量 0 配对、控制和汇总。官方 `schedule_step1.py`、`schedule_step2.py`、`schedule_step3.py`、`evaluation_validation.py`、三个 `multicore_cut_evaluate_problem_*.py` 和 `singlecore_evaluate.py` 均保持原字节，不在 Idea 阶段修改。

## 12. 实际来源、未测事项与版本变化

### 12.1 实际来源

- 题面：`2026参赛工作区/inputs/problem/A题/通用神经网络处理器下的多核调度问题.docx`，重点为 §1.3--1.5、问题 1--3、附录 B.4--B.6、C--D。
- 附件总说明：`2026参赛工作区/inputs/raw/A题/附件/README.md`；固定配置：`data/config.txt`。
- 代码：`code/multicore_cut_evaluate_problem_1.py` 的 `_build_scene_a_tasks`、`task_release_time`；`multicore_cut_evaluate_problem_2.py` 的 `_build_scene_b_tasks`、`external_release`、`_prioritize_task_seq`；`multicore_cut_evaluate_problem_3.py` 的 `read_cache_config`、`copy_tensor_info`、`insert_cache`、`retire`、`issue`；以及 `schedule_step1.py`、`schedule_step2.py`、`schedule_step3.py`、`evaluation_validation.py`、`contest_io.py`。
- 100 个原始 JSON：`data/case_001.json`--`data/case_100.json`，本轮只读统计了操作数、张量数和计算依赖分量。
- 方法文献：第 3 节 R1、R2；HEFT、Graham 与 Belady 仅作背景和术语边界。

### 12.2 未测事项

本轮没有启动官方评估器、Step1--3、计时实验、批量求解、Cache 全量回放或长时间搜索。因此 $T_1$、真实 Makespan、Spill/Reload、代理后悔值、空核等价性在全量输入上的成立范围、C(0) 与 B 的差异和 8 小时可达性均留到第 9 节的第一步或后续实验。静态统计支持候选结构和规模档，不支持实际瓶颈、全局最优或性能收益结论。

### 12.3 本版 17 项意见的处理索引

| 意见 | 处理位置与结论 |
|---:|---|
| 1 | §4.3、§8、§9.1：A/B 分别做补空核和单核保底检查；C 不推广；失败按实际结果保留，补评计入槽位。 |
| 2 | §2.2、§6.1、§6.2、§7.1：给出 K=2--5 的 16/16/16/16 统计；识别公共前段、支路和汇合段，A/B 重算共享输入域并有限退化。 |
| 3 | §6.3、§6.4、§9.4：按规模固定多轮轻量改进、轮数和候选上限；补明 A/B 普通轻量元组、容量独立排序、$L_{\rm cap}$ 和严格接受条件；方法称受 FM 思想启发的有界局改。 |
| 4 | §9.1、§9.3--§9.4：第一步先做最小/中位/最大图官方入口计时，21 个观测附着于冻结 V1/单核计划，另有每图 C K=5 冷/暖复测 6 槽；未测只给吞吐阈值。 |
| 5 | §4.2、§6.5、§9.3--§9.5：V1 第一槽先全量覆盖，V2 只读取 V1 的 `initial_candidates`、首槽计划、结果和 prepared 状态，第二槽不回写初始化链；严格独立热链另计。 |
| 6 | §5.1：统一变量范围、商图秩和同核序；A 才合并 Task 顺序，B/C 最终用扩展执行图检查。 |
| 7 | §5.1：保留 $b$ 的精确析取，给出完整线性化；单向下界不得直接用于 COPY；整体仍含确定执行递推。 |
| 8 | §5.2、§7.3--7.4：统一 $Q^0,Q^{\rm spill},Q^{\rm add}$；C 分开 DDR/Cache 两池，有限候选比较，默认 $\varepsilon=0.01$ 只展示同集合折中。 |
| 9 | §5.4：用合法 K=2、整数周期、独立 M 操作的 Partition 归约说明弱 NP 难；固定 100 图不作复杂度证明。 |
| 10 | §6.1、§7.2：R 只在 H 前 8 个就绪操作中比较释放净字节；去容量控制改用 H，并同步起点和伪代码。 |
| 11 | §3、§12.1：列出 HEFT、Graham、Belady 的作者/题名/年份/页码和可用范围；不把它们当空核或 Step2 正确性证明。 |
| 12 | §2.2、§2.3、§5.4、§9.2：保留实际静态计数和 $r>1/K$ 条件；逐例 $T_1/LB_1$ 与路径比值留待实测。 |
| 13 | §4.2、§9.2：全部 A/B 组合保存第一槽与最终槽，报告增益、胜率、失败和耗时；局部收益与独立 V1 消融分开。 |
| 14 | §9.2、§10：六代表和 K=2/5 控制覆盖结构范围；补齐轻量代理 A 的 $P_A^0$、$J_A^{\rm light}$ 和评分元组，报告配对差异与失败，不扩全量控制矩阵。 |
| 15 | §7.4、§9.1、§9.5：相同输入/XB/K/配置做 C(0) 与 B 配对；相等或不等都按事件证据报告，不建全量零容量基线。 |
| 16 | §9.1、§9.5：等价性和计时先行；12 个机制微图合并核算；四天内早完成 V1，再运行 V2。 |
| 17 | §6.3、§7.1：A 单操作新 Task 只有跨域/关键路径/容量触发且轻量改善才进入，受每轮 8 个和总候选上限限制。 |

### 12.4 五组关键表述变化

1. 原“第二次比较只由局部代理严格改善触发”改为“第二位置从严格改善局部候选与已完成 profile 的不同初始方案合并池中确定”，并在同一槽位上计费。
2. 原“C 将图输入轻量搬运相加为一个主时间”改为“DDR 与 Cache 工作量分别进入主评分最大值，合计只作次级字段”；R 顺序也改为先限关键路径，再比较释放净字节。
3. 原“分量不足 K 时默认寻找 K 个前缀分量、A 固定枚举单操作新 Task”改为“识别公共前段、合法支路和汇合段；单操作只有跨域/关键路径/容量触发且轻量严格改善时保留，条件不成立时有限退化”。
4. 原“V1/V2 共用结果而不增加调用”改为“V1 第一槽先完成全量覆盖，V2 复用同计划状态占第二槽；C 冻结 V1 的 B 赢家，不同热链和严格独立诊断另计”。
5. 原“A/B 轻量阶段只写数值代理字段、轻量 A 控制没有公式”改为“普通 A/B 使用 $(J_{A/B}^{\rm light},Q^0,\operatorname{plan\_key})$，容量候选单独按压力排序并经 $L_{\rm cap}$ 入池；轻量代理 A 使用 $(J_A^{\rm light},Q_A^0,P_A^0,\operatorname{plan\_key})$，共同规则集中在 §6.3--§6.4”。

本文件只完成 Idea 设计、静态源码/题面阅读、公式推导、说明性手算和预算设计；未执行下一阶段求解器、官方评估、计时或批量实验。
