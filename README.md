# FastAPI Water Knowledge Graph API / FastAPI 水资源知识图谱接口

A minimal FastAPI service that queries Neo4j for reservoir information and answers simple natural-language questions.

一个轻量级 FastAPI 服务，用于查询 Neo4j 中的水库信息，并回答简单自然语言问题。

## Features / 功能特性

- `GET /ping`: health check / 健康检查
- `GET /reservoir/{name}`: query a reservoir node by name / 按名称查询水库节点
- `POST /ask`: rule-based question answering for selected reservoir attributes / 基于规则的属性问答
- Optional LLM fallback for unmatched questions / 未命中规则时可选大模型兜底

## Project Structure / 项目结构

- `main.py`: FastAPI app wiring and routes / FastAPI 应用装配与路由入口
- `config.py`: Neo4j config and Cypher execution helper / Neo4j 配置与 Cypher 执行工具
- `qa_service.py`: question parsing and rule-based QA pipeline / 问句解析与规则问答流程
- `tests/test_qa_service.py`: lightweight regression tests for key QA branches / 关键问答分支的轻量回归测试

## Requirements / 运行要求

- Python 3.10+
- Neo4j running on `bolt://localhost:7687` / Neo4j 运行地址为 `bolt://localhost:7687`
- Neo4j credentials provided by environment variables (`NEO4J_PASSWORD` is required) / 通过环境变量提供 Neo4j 凭据（`NEO4J_PASSWORD` 必填）

## Environment Variables / 环境变量

- `NEO4J_URI` (optional, default: `bolt://localhost:7687`) / 可选，默认 `bolt://localhost:7687`
- `NEO4J_USER` (optional, default: `neo4j`) / 可选，默认 `neo4j`
- `NEO4J_PASSWORD` (required) / 必填
- `LLM_ENABLED` (optional, default: `false`) / 可选，默认 `false`
- `LLM_BACKEND` (optional, default: `cloud`) / 可选，默认 `cloud`
- `LLM_API_KEY` (required when LLM enabled) / 启用 LLM 时必填
- `LLM_BASE_URL` (optional, OpenAI-compatible endpoint) / 可选，OpenAI 兼容网关
- `LLM_MODEL` (optional, default: `gpt-4o-mini`) / 可选，默认 `gpt-4o-mini`
- `LLM_TIMEOUT_SECONDS` (optional, default: `15`) / 可选，默认 `15`

## Quick Start (PowerShell) / 快速开始（PowerShell）

```powershell
cd "D:\Learn\FastAPIProject"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:NEO4J_PASSWORD = "your_neo4j_password"
# Optional: enable LLM fallback / 可选：开启 LLM 兜底
$env:LLM_ENABLED = "true"
$env:LLM_API_KEY = "your_api_key"
$env:LLM_MODEL = "gpt-4o-mini"
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Open docs at / 文档地址：

- `http://127.0.0.1:8000/docs`

## API Examples (PowerShell) / 接口示例（PowerShell）

Health check / 健康检查：

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/ping"
```

Query reservoir / 查询水库：

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/reservoir/三峡水库"
```

Ask question / 发起问答：

```powershell
$body = @{ text = "三峡水库的装机容量是多少" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/ask" -ContentType "application/json" -Body $body
```

## Test / 测试

```powershell
python -m pytest -q
```

`qa_service.py` also provides `refresh_dynamic_alias_cache()` for manual cache refresh after reservoir data updates.

`qa_service.py` 还提供 `refresh_dynamic_alias_cache()`，可在水库数据更新后手动刷新别名缓存。

## Notes / 说明

- If Neo4j is unavailable, API endpoints that query Neo4j return a `503` error. / 如果 Neo4j 不可用，相关接口会返回 `503`。
- If `NEO4J_PASSWORD` is missing, Neo4j query endpoints return a `503` error with a configuration hint. / 如果缺少 `NEO4J_PASSWORD`，相关接口会返回带配置提示的 `503`。
- `POST /ask` remains rule-first; LLM is only used as optional fallback when rule answers are unavailable. / `POST /ask` 仍以规则优先，只有规则无法回答时才会尝试大模型兜底。


