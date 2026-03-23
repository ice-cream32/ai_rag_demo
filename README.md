# 存储芯片知识库 AI（Lite）

基于 FastAPI + LangChain Agent + 阿里云百炼（DashScope）+ 阿里云 OSS 向量索引的后端服务。

当前版本是纯后端 API 形态，核心能力为：
- 智能问答（Agent 统一入口）
- 料号解析/参数计算/对比/BOM（通过 Agent Tools）
- 文档上传与向量化入库

---

## 1. 技术栈

| 组件 | 选型 |
|---|---|
| Web 框架 | FastAPI + Uvicorn |
| Agent | LangChain `create_agent` |
| LLM | DashScope OpenAI 兼容接口 |
| Embedding | sentence-transformers（本地） |
| 向量库 | 阿里云 OSS V2 Vector Index |
| 文档处理 | LangChain Community + PyMuPDF |

---

## 2. 当前 API 概览

### 健康检查
- `GET /health`

### 对话入口
- `POST /api/v1/chat`

### 文档管理
- `POST /api/v1/documents/upload`（兼容保留，不推荐）
- `POST /api/v1/documents/index-directory`
- `GET /api/v1/documents/stats`

### 统一上传入口（推荐）
- `POST /api/v1/uploads/unified`

### 规则学习（Rule Learning）
- `POST /api/v1/rules/import-xlsx`（兼容保留，不推荐）
- `GET /api/v1/rules`
- `POST /api/v1/rules/parse`
- `POST /api/v1/rules/learn-from-file`（兼容保留，不推荐）
- `POST /api/v1/rules/learn-from-text`（兼容保留，不推荐）

### OpenAI-Compatible
- `GET /v1/models`
- `POST /v1/chat/completions`（支持 `stream=true` SSE）

> 说明：
> - 原业务接口默认使用 `X-API-Key`
> - `/v1/*` 推荐使用 `Authorization: Bearer <API_KEY>`，同时兼容 `X-API-Key`

---

## 3. 快速启动

### 3.1 环境要求
- Python 3.11（推荐）
- macOS / Linux

### 3.2 安装依赖

```bash
cd knowledge_ai_lite
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

> 兼容性建议（如遇 NumPy/Torch 版本冲突导致启动失败）：
>
> ```bash
> pip install numpy==1.26.4 sentence-transformers==3.4.1
> ```

### 3.3 配置 `.env`

在项目根目录创建 `.env`，至少配置以下参数（变量名需与代码一致）：

```env
# API
API_HOST=0.0.0.0
API_PORT=8000
API_DEBUG=false
API_WORKERS=1
API_KEY=your_api_key
LOG_LEVEL=INFO

# DashScope
DASHSCOPE_API_KEY=your_dashscope_key
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_MODEL=qwen-plus
DASHSCOPE_TEMPERATURE=0.1
DASHSCOPE_MAX_TOKENS=4096

# OpenAI-Compatible
OPENAI_COMPAT_ENABLED=true
OPENAI_COMPAT_MODEL_ID=先搜小芯
OPENAI_COMPAT_MODEL_NAME=Knowledge AI Agent

# Embedding
EMBEDDING_MODEL=paraphrase-multilingual-mpnet-base-v2
EMBEDDING_DIMENSION=768

# OSS Vector
ALIYUN_OSS_ACCESS_KEY_ID=xxx
ALIYUN_OSS_ACCESS_KEY_SECRET=xxx
ALIYUN_OSS_ENDPOINT=https://oss-cn-xxx.aliyuncs.com
ALIYUN_OSS_BUCKET_NAME=xxx
ALIYUN_REGION=cn-xxx
ALIYUN_ACCOUNT_ID=xxx
ALIYUN_COLLECTION_NAME=semiconductordocs

# RAG
DATA_DIR=./data/documents
CHUNK_SIZE=800
CHUNK_OVERLAP=150
RAG_TOP_K=5
RAG_MIN_SIMILARITY=0.3
```

### 3.4 启动服务

```bash
API_WORKERS=1 .venv/bin/python main.py
```

启动后访问：
- Swagger: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

---

## 4. 调用示例

### 4.1 健康检查

```bash
curl -s http://127.0.0.1:8000/health
```

### 4.2 聊天（带 API Key）

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/chat" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: your_api_key" \
    -d '{
        "query": "解析料号 PRN256M8V00HK8DA-12K",
        "chat_history": []
    }'
```

### 4.3 上传文档（统一入口）

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/uploads/unified" \
    -H "X-API-Key: your_api_key" \
    -F "action=document_upload" \
    -F "file=@./data/documents/test_doc.md" \
    -F "category=demo"
```

### 4.4 导入规则 xlsx（统一入口）

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/uploads/unified" \
    -H "X-API-Key: your_api_key" \
    -F "action=rules_import_xlsx" \
    -F "file=@./data/rule_learning/examples/rule_learning_example.xlsx"
```

### 4.5 列出规则

```bash
curl -s "http://127.0.0.1:8000/api/v1/rules" \
    -H "X-API-Key: your_api_key"
```

### 4.6 解析料号（本地优先，可联网补全）

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/rules/parse" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: your_api_key" \
    -d '{
      "part_number": "PRN256M8V00HK8DA-12K",
      "brand_hint": "Micron",
      "enable_web_enrich": true
    }'
```

### 4.7 从文本学习规则（统一入口）

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/uploads/unified" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: your_api_key" \
    -d '{
      "action": "rules_learn_text",
      "text": "规则: prefix PRN 映射 product_type=DDR, 示例 PRN256M8V00HK8DA-12K",
      "source_name": "inline_demo"
    }'
```

### 4.8 从文件学习规则（统一入口）

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/uploads/unified" \
    -H "X-API-Key: your_api_key" \
    -F "action=rules_learn_file" \
    -F "file=@./data/rule_learning/examples/learn_from_file_example.md"
```

### 4.9 统一上传入口（整合文档上传/规则导入/规则学习）

通过 `action` 参数区分能力：
- `document_upload`: 文档上传并向量化（`file` 必填，可选 `category`）
- `rules_import_xlsx`: 规则 xlsx 导入（`file` 必填）
- `rules_learn_file`: 从文件学习规则（`file` 必填）
- `rules_learn_text`: 从文本学习规则（`text` 必填，可选 `source_name`）

示例 1：统一入口上传文档

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/uploads/unified" \
    -H "X-API-Key: your_api_key" \
    -F "action=document_upload" \
    -F "file=@./data/documents/test_doc.md" \
    -F "category=demo"
```

示例 2：统一入口导入规则 xlsx

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/uploads/unified" \
    -H "X-API-Key: your_api_key" \
    -F "action=rules_import_xlsx" \
    -F "file=@./data/rule_learning/examples/rule_learning_example.xlsx"
```

示例 3：统一入口从文件学习规则

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/uploads/unified" \
    -H "X-API-Key: your_api_key" \
    -F "action=rules_learn_file" \
    -F "file=@./data/rule_learning/examples/learn_from_file_example.md"
```

示例 4：统一入口从文本学习规则（JSON）

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/uploads/unified" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: your_api_key" \
    -d '{
      "action": "rules_learn_text",
      "text": "规则: prefix PRN 映射 product_type=DDR, 示例 PRN256M8V00HK8DA-12K",
      "source_name": "inline_demo"
    }'
```

> 兼容性说明：
> - 旧接口 `POST /api/v1/documents/upload`、`POST /api/v1/rules/import-xlsx`、`POST /api/v1/rules/learn-from-file`、`POST /api/v1/rules/learn-from-text` 继续保留。

---

## 5. 目录结构（当前）

```text
knowledge_ai_lite/
├── main.py
├── README.md
├── requirements.txt
├── app/
│   ├── main.py
│   ├── config.py
│   ├── agent/
│   │   ├── agent.py
│   │   ├── skills.py
│   │   ├── part_number_parser.py
│   │   └── rule_learning/
│   │       ├── excel_importer.py
│   │       ├── rule_repository.py
│   │       ├── local_matcher.py
│   │       ├── parser.py
│   │       ├── web_enricher.py
│   │       ├── image_searcher.py
│   │       ├── conflict_detector.py
│   │       └── rule_updater.py
│   ├── api/
│   │   ├── chat.py
│   │   ├── documents.py
│   │   └── rules.py
│   ├── embeddings/
│   ├── loader/
│   ├── retriever/
│   ├── vectorstore/
│   └── openai_compat/
├── tests/
│   └── test_rule_learning.py
├── scripts/
│   └── generate_rule_learning_example_xlsx.py
└── data/
    ├── documents/
    └── rule_learning/
        └── examples/
            └── rule_learning_example.xlsx
```

---

## 6. 生产建议

- `API_DEBUG=false`
- 初始 `API_WORKERS=1`（避免内存不足导致进程被系统杀死，常见退出码 137）
- 对外建议通过 Nginx 反向代理，仅暴露 80/443
- 为 `API_KEY` 使用高强度随机值

---

## 7. 常见问题

### Q1: 服务启动后很快退出，退出码 137
通常是内存不足或 worker 过多，优先将 `API_WORKERS` 调小到 `1`。

### Q2: 接口返回 401
检查请求头是否携带正确的 `X-API-Key`。

### Q3: 文档上传成功但检索不到
检查 OSS 配置、向量索引名、以及 `RAG_MIN_SIMILARITY` 是否过高。

### Q4: 启动时报 NumPy / Torch / sentence-transformers 兼容错误
请确认使用 Python 3.11 的虚拟环境，并执行：

```bash
source .venv/bin/activate
pip install numpy==1.26.4 sentence-transformers==3.4.1
```

---

## 8. OpenAI-Compatible 联调（Open WebUI）

当前已支持 OpenAI-compatible 端点：
- `GET /v1/models`
- `POST /v1/chat/completions`（支持 `stream=true` SSE）

### 8.1 Open WebUI 配置

在 Open WebUI 的 OpenAI 连接配置中填写：
- **API Base URL**: `http://<你的服务地址>:8000/v1`
- **API Key**: 你的 `API_KEY`

认证兼容说明：
- 推荐使用 `Authorization: Bearer <API_KEY>`（OpenAI 标准）
- 同时兼容 `X-API-Key: <API_KEY>`

### 8.2 模型列表验证

```bash
curl -s -H "Authorization: Bearer your_api_key" \
    http://127.0.0.1:8000/v1/models
```

预期返回包含：
- `object = "list"`
- `data[0].id = 先搜小芯`（可由配置覆盖）

### 8.3 聊天验证（非流式）

```bash
curl -s -X POST "http://127.0.0.1:8000/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer your_api_key" \
    -d '{
        "model":"先搜小芯",
        "messages":[{"role":"user","content":"你好"}],
        "stream":false
    }'
```

### 8.4 聊天验证（流式 SSE）

```bash
curl -N -s -X POST "http://127.0.0.1:8000/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer your_api_key" \
    -d '{
        "model":"先搜小芯",
        "messages":[{"role":"user","content":"请分三点介绍你的能力"}],
        "stream":true
    }'
```

流式返回格式为 OpenAI chunk：
- `object = "chat.completion.chunk"`
- `choices[0].delta.content`
- 结束标记：`data: [DONE]`

响应头会返回：
- `X-Request-Id`（用于链路追踪）

---

## 9. OpenAI-Compatible 测试清单（curl）

### 9.1 认证通过（Bearer）

```bash
curl -s -H "Authorization: Bearer your_api_key" http://127.0.0.1:8000/v1/models
```

### 9.2 认证通过（X-API-Key 兼容）

```bash
curl -s -H "X-API-Key: your_api_key" http://127.0.0.1:8000/v1/models
```

### 9.3 认证失败

```bash
curl -s -H "Authorization: Bearer wrong_key" http://127.0.0.1:8000/v1/models
```

### 9.4 模型不存在

```bash
curl -s -X POST "http://127.0.0.1:8000/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer your_api_key" \
    -d '{
        "model":"not-exist",
        "messages":[{"role":"user","content":"hi"}],
        "stream":false
    }'
```

### 9.5 请求参数错误（空 messages）

```bash
curl -s -X POST "http://127.0.0.1:8000/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer your_api_key" \
    -d '{
        "model":"先搜小芯",
        "messages":[],
        "stream":false
    }'
```

### 9.6 多轮对话映射验证

```bash
curl -s -X POST "http://127.0.0.1:8000/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer your_api_key" \
    -d '{
        "model":"先搜小芯",
        "messages":[
            {"role":"user","content":"我叫张三"},
            {"role":"assistant","content":"你好张三"},
            {"role":"user","content":"你还记得我叫什么吗？"}
        ],
        "stream":false
    }'
```

---

## 10. 规则学习 API 使用说明

### 10.1 示例 xlsx

项目内已提供示例文件：
- `data/rule_learning/examples/rule_learning_example.xlsx`

也可以重新生成：

```bash
source .venv/bin/activate
.venv/bin/python scripts/generate_rule_learning_example_xlsx.py
```

### 10.1.1 学习示例文件（Phase 6）

项目内已提供学习接口示例输入：
- `data/rule_learning/examples/learn_from_file_example.md`
- `data/rule_learning/examples/learn_from_text_example.txt`

### 10.2 导入规则

推荐：`POST /api/v1/uploads/unified` + `action=rules_import_xlsx`

兼容：`POST /api/v1/rules/import-xlsx`

返回关键字段：
- `total_rows / parsed_rows / skipped_rows`
- `created_rules / updated_rules`
- `by_brand`

### 10.3 本地优先解析

`POST /api/v1/rules/parse`

请求参数：
- `part_number`：必填
- `brand_hint`：可选
- `enable_web_enrich`：可选，默认 `true`

解析行为：
1. 先用本地 xlsx 规则匹配与解析
2. 本地字段缺失时再尝试联网补全
3. 联网补全仅补充缺失字段，不覆盖本地字段
4. 自动产出更新日志与冲突日志（若有）

### 10.4 学习接口与报告字段

推荐：`POST /api/v1/uploads/unified`
- `action=rules_learn_file`（文件学习）
- `action=rules_learn_text`（文本学习）

兼容：`POST /api/v1/rules/learn-from-file` 与 `POST /api/v1/rules/learn-from-text`

返回统一学习报告：
- `learning_id` / `created_at`
- `source`: `name` / `input_type` / `chunks_count` / `warnings`
- `pipeline`: `candidates_count` / `normalized_count` / `validated_total`
- `result`: `accepted_count` / `rejected_count` / `conflicts_count` / `accepted_rule_ids` / `rejected` / `conflicts`
- `duration_ms`

---

## 11. 测试说明

### 11.1 运行单元测试

```bash
source .venv/bin/activate
.venv/bin/python -m unittest discover -s tests -v
```

当前测试覆盖：
- xlsx 导入与规则列表
- 本地规则优先解析
- 学习服务报告结构校验
- `learn-from-text` 接口（成功与空文本校验）
- `learn-from-file` 接口（文件上传学习）

### 11.2 规则学习相关数据文件

运行解析后会在 `data/rule_learning/` 生成或更新：
- `manual_rules.json`：人工主规则层（xlsx 导入）
- `extension_rules.json`：扩展规则层（候选规则）
- `update_logs.json`：更新日志
- `conflicts.json`：冲突检测结果
