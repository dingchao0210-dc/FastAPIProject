import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List

from fastapi import HTTPException
from py2neo import Graph

SERVICE_UNAVAILABLE_MSG = "知识图谱服务暂时不可用，请稍后再试。"
CONFIG_MISSING_MSG = "Neo4j 配置缺失：请设置环境变量 NEO4J_PASSWORD。"


@dataclass(frozen=True)
class Settings:
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    llm_enabled: bool
    llm_backend: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    llm_timeout_seconds: float


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
        neo4j_password=os.getenv("NEO4J_PASSWORD", "dc20020210").strip(),
        llm_enabled=_env_bool("LLM_ENABLED", True),
        llm_backend=os.getenv("LLM_BACKEND", "cloud").strip().lower(),
        llm_api_key=os.getenv("LLM_API_KEY", "sk-lmjHGu4EvCrcsFrdRlqopxP5cOWzjsG4BsXrkUJ9z0YL77Rt").strip(),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.moonshot.cn/v1").strip(),
        llm_model=os.getenv("LLM_MODEL", "moonshot-v1-8k").strip(),
        llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
    )


@lru_cache(maxsize=1)
def get_graph() -> Graph:
    # 使用懒加载 + 单例缓存，避免每次请求重复创建连接对象。
    settings = get_settings()
    if not settings.neo4j_password:
        raise RuntimeError("missing NEO4J_PASSWORD")
    return Graph(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))


def run_cypher(cypher: str, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
    # 统一图查询入口：所有 Cypher 都走参数化执行，异常统一映射为 503。
    try:
        return get_graph().run(cypher, parameters=parameters).data()
    except RuntimeError as exc:
        if "NEO4J_PASSWORD" in str(exc):
            raise HTTPException(status_code=503, detail=CONFIG_MISSING_MSG)
        raise HTTPException(status_code=503, detail=SERVICE_UNAVAILABLE_MSG)
    except Exception:
        raise HTTPException(status_code=503, detail=SERVICE_UNAVAILABLE_MSG)


