# 电商 SQL 数据分析 Agent：简历与面试说明

> 分析基于当前仓库 v2.0 源码、配置、前端、测试、评测集和正在运行的 Docker 环境。本文只描述代码中真实存在并已核验的能力。

## 一、项目整体理解

### 1. 项目名称

**电商 SQL 数据分析 Agent（Natural Language to SQL Analytics Workbench）**

### 2. 项目解决的问题

业务人员通常不知道数据库表结构和 SQL，直接把生产数据库开放给大模型又存在误写、越权、慢查询和结果编造风险。本项目将中文经营问题转换为 PostgreSQL 查询，在执行前完成语义意图拦截和 SQL AST 安全校验，再通过独立只读账号执行，最终返回基于真实结果的中文结论、图表、数据表和可审计记录。

### 3. 应用场景

- 电商运营查询 GMV、订单量、客单价、退款率和复购客户等指标。
- 内部分析人员进行临时取数、趋势分析和查询结果导出。
- 管理员对演示或小批量经营数据进行 CSV/XLSX 补数。
- 接入单个已授权 PostgreSQL 分析库的内部试用工作台。

不适合直接作为公网多租户 SaaS，也不替代企业级 BI、ETL、数据治理或备份平台。

### 4. 核心功能

1. 中文问题生成 PostgreSQL `SELECT/WITH` 查询。
2. 强制 DeepSeek Function Calling 调用唯一工具 `run_sql`。
3. SQLGlot AST 白名单校验、Schema/Table allowlist、危险函数拦截。
4. 只读数据库账号、只读事务、5 秒超时、最大 200 行结果。
5. SQL 失败后把错误反馈给模型，最多自动修正一次。
6. 基于真实查询结果生成中文摘要，并展示原生 SVG 图表和数据表。
7. 保存问题、SQL、结果、状态、耗时、尝试次数和错误 Trace。
8. HttpOnly 签名会话、按用户查询限流、历史结果复查和 CSV 导出。
9. 管理员 CSV/XLSX 预览、字段校验、主键 Upsert 和导入审计。
10. Docker Compose 隔离部署、健康检查、虚构电商数据生成和在线评测集。

### 5. 用户使用流程

```text
用户登录
  ↓
输入中文经营问题
  ↓
服务端校验问题长度、登录状态、调用频率和危险意图
  ↓
DeepSeek 读取 System Prompt、动态 Schema 和业务指标口径
  ↓
模型以 Function Calling 生成 run_sql(sql)
  ↓
SQLGlot 解析 AST，检查单语句、只读类型、Schema、表和危险函数
  ↓
追加结果行数限制，使用 analytics_reader 开启只读事务并执行
  ↓
成功：DeepSeek 根据真实结果生成中文摘要
失败：错误返回模型，最多修正 SQL 一次
  ↓
返回 SQL、摘要、表格和图表，并保存 Trace
```

## 二、Agent 架构分析

### 1. 是否属于 AI Agent

**结论：属于边界明确、单工具、受约束的 Tool-Calling Agent。**

它不只是调用一次 LLM 生成文本，而是让模型选择工具参数（SQL），由程序执行真实数据库工具，把工具错误反馈给模型并形成最多两轮的闭环。它具备“模型推理 + 工具调用 + 环境反馈 + 修正控制流”。

它不是：

- 多 Agent 系统；
- LangGraph 状态图；
- 带长期偏好记忆的对话 Agent；
- RAG/向量检索系统；
- 能自主拆分任意复杂任务的通用 Agent。

### 2. 分层架构

| 模块 | 实际实现 |
|---|---|
| 用户输入层 | 原生 HTML/CSS/JavaScript，提供登录、自然语言输入、历史查询和管理员导入页面 |
| API 层 | FastAPI 提供认证、分析、历史、导入、Schema 和健康检查接口 |
| LLM 推理层 | DeepSeek OpenAI 兼容 Chat Completions API |
| Prompt 设计 | System Prompt 注入角色、只读规则、动态表结构和业务口径；摘要阶段使用独立约束 Prompt |
| Agent 规划模块 | 没有独立 Planner；模型只完成“问题到 SQL”的隐式单步规划 |
| Tool 调用模块 | JSON Schema 定义 `run_sql`，通过 `tool_choice` 强制调用 |
| 控制流 | 手写 `while attempts < 2` 循环；成功结束，失败反馈工具错误并允许一次修正 |
| SQL 安全层 | 问题意图正则拦截 + SQLGlot AST 白名单 + 数据库只读权限三层防护 |
| 数据处理层 | SQLAlchemy/psycopg 执行查询，Decimal/日期 JSON 化，图表类型推断 |
| Memory 模块 | PostgreSQL 保存 QueryTrace 和 ImportJob；属于审计历史，不会回填给模型，因此不是对话记忆 |
| RAG 模块 | 不存在。Schema 和 Markdown 业务口径是直接上下文注入，不含检索、Embedding 或向量库 |
| 输出层 | 中文摘要、生成 SQL、表格、SVG 图表、CSV 和历史详情 |

### 3. Agent 工作流程

```text
用户请求
  ↓
Agent 校验请求意图
  ↓
LLM 结合动态 Schema 和业务口径理解问题
  ↓
隐式规划 SQL
  ↓
Function Calling 请求 run_sql
  ↓
程序校验 SQL AST 和访问范围
  ↓
只读 PostgreSQL 工具执行
  ├─ 成功 → LLM 基于真实结果总结 → 返回并保存 Trace
  └─ 失败 → 错误作为 Tool Message 回传 → 修正一次 → 成功或终止
```

### 4. AI 技术及作用

**技术：DeepSeek LLM**  
**作用：**理解中文经营问题、生成 PostgreSQL 查询，并根据真实查询结果输出简洁中文分析。

**技术：Prompt Engineering**  
**作用：**System Prompt 约束角色、SQL 类型、Schema 范围、金额精度和时间顺序；动态加入实际表结构与业务指标定义，降低字段幻觉和口径错误。

**技术：Function Calling / Tool Calling**  
**作用：**将数据库执行封装为 `run_sql` 工具；模型只负责生成结构化 SQL 参数，应用掌握实际执行权和安全边界。

**技术：错误反馈修正循环**  
**作用：**SQL 解析、越权校验或数据库执行失败时，将清洗后的错误作为 Tool Message 回传，允许模型最多修正一次，避免无限循环和费用失控。

**技术：Workflow 设计**  
**作用：**使用手写有限状态流程实现“生成—校验—执行—修正—总结”，没有引入 LangChain/LangGraph，减少第一版依赖和调试复杂度。

**技术：RAG / Embedding / Vector Database**  
**作用：**项目未使用。业务口径文件整体注入 Prompt，数据查询直接由 SQL 工具完成。

**技术：Memory**  
**作用：**仅将查询和导入过程持久化为审计历史，不参与后续模型推理；不能包装成“长期记忆”。

**技术：Agent Framework**  
**作用：**未使用专用 Agent 框架；基于 OpenAI Python SDK 和应用代码实现轻量 Tool-Calling Loop。

## 三、代码技术栈

### 后端

**技术：Python 3.12**  
**作用：**实现 Agent 控制流、SQL 校验、数据处理、认证和评测脚本。

**技术：FastAPI + Uvicorn**  
**作用：**提供 REST API、依赖注入、生命周期初始化、静态页面托管和健康检查。

**技术：Pydantic**  
**作用：**校验登录和自然语言查询请求的字段长度。

### AI 与数据分析

**技术：DeepSeek OpenAI 兼容 API / OpenAI Python SDK**  
**作用：**完成 SQL Tool Calling 和结果摘要生成。

**技术：SQLGlot**  
**作用：**把 SQL 解析为 PostgreSQL AST，拒绝多语句、写操作、越权表和危险函数，并规范化 SQL。

**技术：原生 SVG + JavaScript**  
**作用：**根据时间或类别字段自动生成折线图/柱状图，不依赖前端图表框架。

### 数据存储

**技术：PostgreSQL 17**  
**作用：**保存 7 张电商业务表，以及查询 Trace 和导入审计记录。

**技术：SQLAlchemy 2 + psycopg 3**  
**作用：**ORM 建模、数据库连接池、事务、动态 Schema 检查、只读查询和 PostgreSQL Upsert。

**技术：CSV / OpenPyXL**  
**作用：**解析 UTF-8/GB18030 CSV 和 XLSX，完成类型转换、预览和小批量数据导入。

### 安全与部署

**技术：HMAC-SHA256 HttpOnly Cookie**  
**作用：**实现带过期时间的签名会话，防止客户端篡改身份。

**技术：Docker / Docker Compose**  
**作用：**隔离 API 与 PostgreSQL，固定 8010 端口、独立网络和 Volume，配置服务健康检查与自动重启策略。

**技术：最小权限数据库账号**  
**作用：**Owner 账号只用于初始化、审计和管理员导入；Agent 查询始终通过 `analytics_reader`，同时使用数据库默认只读、事务只读和超时限制。

**技术：pytest / unittest**  
**作用：**覆盖 SQL 安全、危险问题、会话签名、配置校验、图表选择、项目隔离和导入解析授权。

## 四、项目技术亮点（简历语言）

1. **基于 DeepSeek Function Calling 自研单工具 SQL Agent 控制流**，通过强制工具调用和有限重试实现“自然语言生成 SQL—执行反馈—自动修正—结果总结”闭环，避免模型直接编造经营结论。
2. **设计三层只读安全体系**：问题意图拦截、SQLGlot AST 白名单和 PostgreSQL 最小权限账号，叠加 Schema/Table allowlist、5 秒超时和 200 行限制，降低越权、误写和慢查询风险。
3. **实现数据结构与业务口径动态注入**，启动时从 PostgreSQL Catalog 验证授权表并构造 Prompt，同时加载可维护的 GMV、退款率等指标定义，减少字段幻觉和业务口径偏差。
4. **构建可追溯的数据分析链路**，持久化问题、SQL、结果、摘要、耗时、重试和错误 Trace，支持用户隔离的历史复查与 CSV 导出，并保留摘要失败时的数据结果降级路径。
5. **完成可独立部署和验证的工程化 MVP**，使用 Docker Compose 隔离 API、数据库和 Volume，提供管理员 CSV/XLSX 事务 Upsert、17 项通过的离线测试和 30 场景真实结果评测框架。

## 五、简历项目描述（200—300 字，可直接使用）

**项目名称：** 电商 SQL 数据分析 Agent  
**项目简介：** 将中文经营问题安全转换为 PostgreSQL 查询并返回可追溯结论。

**项目职责：**

1. 设计 DeepSeek Function Calling 单工具 Agent Loop，实现 SQL 生成、执行反馈与一次纠错。
2. 使用 SQLGlot AST、表白名单和只读账号控制越权与写入，并注入 Schema 和业务口径。
3. 基于 FastAPI、PostgreSQL 实现认证、Trace、导出和管理员数据导入，以 Docker Compose 部署。

**技术栈：** Python、FastAPI、DeepSeek、SQLGlot、PostgreSQL、Docker。

**项目成果：** 支持 7 张表和 5 万订单；17 项测试通过，累计 18 次成功查询，含 1 次自动纠错成功。

## 六、1 分钟项目介绍

我做这个项目的原因是，很多运营问题本质上可以通过 SQL 回答，但业务人员不会写 SQL；如果让大模型直接连接数据库，又容易出现字段幻觉、越权或误写。因此我实现了一个电商 SQL 数据分析 Agent。

整体架构是 FastAPI 接收中文问题，DeepSeek 读取动态数据库 Schema 和业务口径，通过 Function Calling 生成 `run_sql` 工具参数。SQL 不会立即执行，而是先经过问题意图检查和 SQLGlot AST 白名单校验，再由独立只读账号在只读事务中执行，并设置 5 秒超时和 200 行上限。SQL 出错时，系统把错误作为工具消息回传模型，最多自动修正一次；成功后模型只根据真实结果生成中文摘要，前端展示 SQL、表格、图表和 CSV。

我负责 Agent Loop、Prompt、安全执行链路、数据库模型、认证审计、数据导入、前端展示和 Docker 部署。最大难点是同时控制 SQL 安全和分析准确性，所以我采用应用校验与数据库权限双保险，并增加业务口径注入和真实执行结果评测。当前项目已完成 17 项离线测试，并在 5 万级订单数据上稳定运行。

## 七、模拟面试问题与参考答案

### 1. 为什么使用 Agent，而不是直接让模型生成 SQL？

直接生成 SQL 只有模型输出，没有受控执行和环境反馈。这个项目需要查询真实数据库、校验权限、处理 SQL 错误并根据结果生成结论，因此使用 Tool Calling Agent 更合适。模型负责理解和生成候选 SQL，应用负责校验和执行，失败后把错误反馈给模型修正，形成闭环。

### 2. 它和普通 ChatBot 有什么区别？

普通 ChatBot 主要根据上下文生成文本，无法证明数值来自真实数据。本项目强制模型调用 `run_sql`，只有工具成功执行后才生成摘要；系统还有 SQL AST 校验、数据库只读权限、失败重试和 Trace。因此它是面向明确业务目标的受约束 Agent，而不是自由聊天机器人。

### 3. Prompt 是如何设计的？

Prompt 分两阶段。SQL 阶段的 System Prompt 定义电商分析角色、只允许 PostgreSQL `SELECT/WITH`、禁止跨 Schema，并动态加入数据库实际列和业务指标口径。摘要阶段使用独立 Prompt，只允许根据 SQL 返回结果总结两到四句，禁止补充结果中不存在的数据。温度分别设为 0 和 0.1，降低随机性。

### 4. Tool Calling 如何实现？

通过 OpenAI SDK定义 `run_sql` Function Schema，参数只有一个 SQL 字符串，并用 `tool_choice` 强制模型调用。服务端解析 `tool_calls[0].function.arguments`，经过 SQLGlot 校验后执行。模型没有数据库连接和写权限，真正的工具执行权始终在应用端。

### 5. 项目是否使用 RAG？如果没有，为什么？

没有使用 RAG、Embedding 或向量数据库。当前知识规模很小：授权表结构来自 PostgreSQL Catalog，业务口径来自一个 Markdown 文件，整体放入 Prompt 即可。引入向量检索会增加依赖和召回不确定性。未来当指标文档、数据字典和案例 SQL 数量显著增长时，才有必要增加带引用的口径检索。

### 6. Memory 如何保存？

项目保存 QueryTrace，包括用户、问题、SQL、结果、摘要、状态、耗时、尝试次数和错误，也保存导入审计。但这些历史目前不回填给模型，所以准确说是“持久化审计历史”，不是对话长期记忆。若后续增加多轮追问，需要设计会话表、上下文裁剪和基于 Trace 的引用机制。

### 7. 如何优化 Agent 效果？

第一是完善业务口径和字段注释；第二是扩充覆盖真实业务问题的黄金评测集，以真实执行结果而不是 SQL 字符串评分；第三是记录错误类型并针对高频错误加入 few-shot SQL 示例；第四是对摘要做数值一致性校验。当前项目已经实现动态 Schema、业务口径、一次纠错和 30 场景评测框架。

### 8. 开发中最大的技术问题是什么？

一类问题是模型 Tool Calling 与 Thinking 模式兼容，因此请求中显式关闭 Thinking；另一类是安全不能只依赖 Prompt，所以增加 SQLGlot AST、allowlist 和数据库只读账号。实际使用还发现导入数据会与原演示数据混合，说明后续需要增加 `dataset_id/import_batch_id`，让查询能够限定数据来源。

### 9. 如何保证输出准确性？

准确性分三层：结构层从真实数据库动态读取表和列；业务层把有效订单、GMV、退款率等口径写入 Prompt；结果层强制执行 SQL 后再总结，并保存 SQL 和数据供人工复查。评测脚本会将 Agent 结果与黄金 SQL 的真实结果做集合比较，而不是只比较 SQL 文本。

### 10. 如果项目扩大，如何改进？

首先接入企业 SSO、RBAC 和行级权限；其次将进程内限流迁移到 Redis，并拆分异步任务以避免模型调用阻塞 API；再增加 Alembic 迁移、集中日志、指标监控和 Trace 保留策略。多数据源场景需要数据源级权限和连接路由；复杂多步分析再考虑 LangGraph，但不会为了框架而框架。

## 八、真实能力边界与改进项

面试时应主动说明：

- 当前是单组织、单账号来源、单分析数据源的内部 MVP，不是多租户 SaaS。
- 没有 LangChain、LangGraph、多 Agent、RAG、Embedding 和向量数据库。
- 没有真正的多轮会话 Memory；历史记录只用于审计和复查。
- 没有企业 SSO、行级权限、Redis 集中限流、异步 Worker、HTTPS 反向代理和正式数据库迁移。
- 摘要最多把前 50 行交给模型，复杂长结果可能需要程序化聚合或一致性校验。
- 管理员导入没有数据批次字段，上传数据会与原数据共同参与查询。
- `start.ps1` 使用前台 Compose，关闭窗口会停止服务；长期使用应改为后台启动或配置系统自启动。
- 30 题在线评测框架已实现，但本次审查未重新执行全量模型评测，不能声称当前模型已达到 80% 正确率。

## 九、当前核验结果

核验时间：2026-07-28。

| 项目 | 实测结果 |
|---|---:|
| API 健康状态 | `ok` |
| DeepSeek 配置 | 已配置 |
| 授权业务表 | 7 张 |
| 分类 / 客户 / 商品 | 11 / 10,006 / 126 |
| 订单 / 订单明细 | 50,010 / 99,983 |
| 支付 / 退款 | 44,997 / 2,882 |
| 成功查询 Trace | 18 |
| 二次尝试后成功 | 1 |
| 失败或被拒绝 Trace | 9 |
| 成功导入记录 | 8 |
| 离线测试 | 17 passed，1 skipped |
| Git 跟踪文件真实 Key 扫描 | 0 条匹配 |

跳过的测试是 Docker 运行镜像中不包含 `docker-compose.yml` 的隔离配置检查，不是功能测试失败。

---

# 《AI Agent 项目简历版总结》

这是一个面向电商经营分析的受约束 SQL Agent。项目使用 DeepSeek Function Calling 将中文问题转为 SQL，通过手写 Agent Loop 完成工具执行、错误反馈和一次自动修正；使用 SQLGlot AST、Schema/Table allowlist、只读数据库账号、事务只读、超时与行数限制构建多层安全边界；结合动态 Schema 和业务口径注入降低字段及指标幻觉。系统基于 FastAPI、SQLAlchemy、PostgreSQL 和 Docker Compose 实现登录限流、Trace 审计、历史导出、SVG 图表与管理员数据导入。项目真实具备 Tool Calling 和有限闭环能力，但不包含 RAG、向量数据库、多 Agent、LangGraph 或长期记忆，适合作为应届生 AI Agent 应用开发岗位的工程化 MVP 项目。
