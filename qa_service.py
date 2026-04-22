from difflib import get_close_matches
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple, cast

from fastapi import HTTPException
from pydantic import BaseModel, Field

from config import SERVICE_UNAVAILABLE_MSG, run_cypher
from llm_service import ask_llm_fallback


class Question(BaseModel):
    # 问答接口的最小输入，仅包含自然语言问题文本。
    text: str = Field(..., min_length=1, max_length=200)


# 维护水库名称别名，值为标准名称。
KNOWN_RESERVOIR_ALIASES: Dict[str, str] = {
    "三峡": "三峡水库",
    "三峡水库": "三峡水库",
    "丹江口": "丹江口",
    "新安江": "新安江",
    "丰满": "丰满",
    "小浪底": "小浪底",
}

COMMON_RESERVOIR_SUFFIXES = ("水库", "水利枢纽")

# 统一节点匹配条件：兼容历史字段 name 和当前库字段 reservoir_name。
RESERVOIR_MATCH_CLAUSE = "MATCH (r:水库) WHERE r.name = $name OR r.reservoir_name = $name"

# 属性关键词映射（中文 -> 图属性名）
# 说明：按插入顺序匹配，长关键词优先；字段名与当前图库属性保持一致。
ATTR_MAPPING: Dict[str, str] = {
    "水库名称": "reservoir_name",
    "名称": "reservoir_name",
    "编号": "reservoir_id",
    "水库编号": "reservoir_id",
    "装机容量": "installed_capacity",
    "防洪库容": "flood_control_capacity",
    "总库容": "total_capacity",
    "库容": "total_capacity",
    "容量": "total_capacity",
    "汛限水位": "flood_limit_level",
    "正常蓄水位": "normal_water_level",
    "正常水位": "normal_water_level",
    "死水位": "dead_water_level",
    "坝型": "dam_type",
    "类型": "dam_type",
    "城市": "city",
    "所在城市": "city",
    "数据来源": "data_source",
    "坝高": "dam_height",
    "建成时间": "construction_year",
    "建成年份": "construction_year",
}

# 关系类问题关键词 -> 候选关系类型（兼容中英命名）
RELATION_MAPPING: Dict[str, List[str]] = {
    "所在省份": ["LOCATED_IN"],
    "省份": ["LOCATED_IN"],
    "所在流域": ["BELONGS_TO_BASIN"],
    "所属流域": ["BELONGS_TO_BASIN"],
    "流域": ["BELONGS_TO_BASIN"],
    "上游": ["上游", "UPSTREAM_OF", "上游来水"],
    "下游": ["下游", "DOWNSTREAM_OF", "下泄"],
    "管理单位": ["管理单位", "MANAGED_BY", "管理方"],
    "水文站": ["MONITORS", "监测", "HAS_STATION", "关联水文站"],
    "监测站": ["MONITORS", "监测", "HAS_STATION", "关联水文站"],
    "测站": ["MONITORS", "监测", "HAS_STATION", "关联水文站"],
}

UNIT_MAPPING: Dict[str, str] = {
    "total_capacity": "亿立方米",
    "flood_control_capacity": "亿立方米",
    "installed_capacity": "万千瓦",
    "flood_limit_level": "米",
    "normal_water_level": "米",
    "dead_water_level": "米",
    "dam_height": "米",
}

SAME_BASIN_KEYWORDS: Tuple[str, ...] = (
    "相同流域",
    "同一流域",
    "同流域",
    "同流域的水库",
)

BASIC_INFO_KEYWORDS: Tuple[str, ...] = ("基本信息", "详情", "介绍", "有哪些属性")
SAME_BASIN_QUERY_HINTS: Tuple[str, ...] = ("水库", "有哪些", "所有")
ANSWER_HANDLER_NAMES: Tuple[str, ...] = (
    "answer_same_basin_reservoirs_question",
    "answer_relation_question",
    "answer_basic_info_question",
)


def query_reservoir(name: str) -> Dict[str, Any]:
    # 精确按 name 命中单个水库节点。
    result = _run_reservoir_query(name, "RETURN r LIMIT 1")
    if not result:
        raise HTTPException(status_code=404, detail="水库不存在")
    # py2neo Node 不是直接可序列化对象，转换为纯字典返回。
    return cast(Dict[str, Any], dict(result[0]["r"]))


def _contains_any(text: str, keywords: Tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _normalize_string_list(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    return [item for item in values if isinstance(item, str) and item]


def _get_alias_mapping() -> Dict[str, str]:
    alias_mapping = dict(KNOWN_RESERVOIR_ALIASES)
    alias_mapping.update(load_dynamic_reservoir_aliases())
    return alias_mapping


def _run_reservoir_query(name: str, return_clause: str, extra_params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"name": name}
    if extra_params:
        params.update(extra_params)
    cypher = f"{RESERVOIR_MATCH_CLAUSE} {return_clause}"
    return run_cypher(cypher, params)


def refresh_dynamic_alias_cache() -> None:
    # 手动刷新缓存，便于数据库更新后无需重启服务。
    load_dynamic_reservoir_aliases.cache_clear()
    load_reservoir_names.cache_clear()


def _build_name_aliases(name: str) -> List[str]:
    aliases = {name}
    for suffix in COMMON_RESERVOIR_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            aliases.add(name[: -len(suffix)])
    return sorted(aliases, key=len, reverse=True)


@lru_cache(maxsize=1)
def load_dynamic_reservoir_aliases() -> Dict[str, str]:
    """Load reservoir aliases from Neo4j and cache in memory."""
    cypher = (
        "MATCH (r:水库) "
        "RETURN DISTINCT coalesce(r.reservoir_name, r.name) AS reservoir_name "
        "ORDER BY reservoir_name"
    )
    try:
        rows = run_cypher(cypher, {})
    except HTTPException:
        return {}

    aliases: Dict[str, str] = {}
    for row in rows:
        canonical = row.get("reservoir_name")
        if not isinstance(canonical, str) or not canonical.strip():
            continue
        canonical = canonical.strip()
        for alias in _build_name_aliases(canonical):
            aliases[alias] = canonical
    return aliases


@lru_cache(maxsize=1)
def load_reservoir_names() -> List[str]:
    # Suggestion pool for name guidance; falls back to static aliases if DB is unavailable.
    dynamic_aliases = load_dynamic_reservoir_aliases()
    if dynamic_aliases:
        return sorted(set(dynamic_aliases.values()), key=len)
    return sorted(set(KNOWN_RESERVOIR_ALIASES.values()), key=len)


def extract_reservoir_name(question: str) -> Optional[str]:
    # 优先匹配更长别名，减少短词抢占（如“容量”/“装机容量”同类问题）。
    alias_mapping = _get_alias_mapping()
    aliases = sorted(alias_mapping.keys(), key=len, reverse=True)
    for alias in aliases:
        if alias in question:
            return alias_mapping[alias]
    return None


def suggest_reservoir_names(question: str, limit: int = 5) -> List[str]:
    names = load_reservoir_names()
    if not names:
        return []

    partial_hits = [name for name in names if question in name or name in question]
    if partial_hits:
        return partial_hits[:limit]

    return get_close_matches(question, names, n=limit, cutoff=0.35)


def extract_attr(question: str) -> Tuple[Optional[str], Optional[str]]:
    for cn, en in ATTR_MAPPING.items():
        if cn in question:
            return cn, en
    return None, None


def answer_relation_question(question: str, reservoir: str) -> Optional[str]:
    # 关系问答模板：根据关系类型筛选邻接节点并聚合名称列表。
    cypher = (
        f"{RESERVOIR_MATCH_CLAUSE} "
        "MATCH (r)-[rel]-(n) "
        "WHERE type(rel) IN $rel_types "
        "RETURN collect(DISTINCT coalesce(n.name, n.名称, toString(id(n)))) AS names"
    )
    for keyword, rel_types in RELATION_MAPPING.items():
        if keyword in question:
            result = run_cypher(cypher, {"name": reservoir, "rel_types": rel_types})
            names = _normalize_string_list(result[0].get("names") if result else [])
            if names:
                return f"{reservoir}的{keyword}是：{', '.join(names)}。"
            return f"未找到{reservoir}的{keyword}相关信息。"
    return None


def answer_basic_info_question(question: str, reservoir: str) -> Optional[str]:
    # 基础信息问答模板：返回节点全部属性并格式化展示。
    if not _contains_any(question, BASIC_INFO_KEYWORDS):
        return None
    result = _run_reservoir_query(reservoir, "RETURN properties(r) AS props LIMIT 1")
    if result and result[0].get("props"):
        props = result[0]["props"]
        text = "，".join([f"{k}: {v}" for k, v in props.items()])
        return f"{reservoir}的基本信息：{text}。"
    return f"未找到{reservoir}的基本信息。"


def answer_same_basin_reservoirs_question(question: str, reservoir: str) -> Optional[str]:
    # 专项问答：查询与目标水库同一流域的所有水库。
    if not _contains_any(question, SAME_BASIN_KEYWORDS):
        return None
    if not _contains_any(question, SAME_BASIN_QUERY_HINTS):
        return None

    cypher = (
        f"{RESERVOIR_MATCH_CLAUSE} "
        "MATCH (r)-[:BELONGS_TO_BASIN]->(b:流域) "
        "MATCH (x:水库)-[:BELONGS_TO_BASIN]->(b) "
        "WITH b.name AS basin, coalesce(x.reservoir_name, x.name) AS reservoir_name "
        "WHERE reservoir_name IS NOT NULL "
        "ORDER BY reservoir_name "
        "RETURN basin, collect(DISTINCT reservoir_name) AS reservoirs"
    )
    result = run_cypher(cypher, {"name": reservoir})
    if not result:
        return f"未找到{reservoir}的流域信息。"

    basin = result[0].get("basin")
    names = _normalize_string_list(result[0].get("reservoirs", []))
    names = [name for name in names if name != reservoir]
    if not names:
        return f"{reservoir}所在流域暂无其他可用水库数据。"
    basin_text = basin if isinstance(basin, str) and basin else "该流域"
    return f"与{reservoir}同属{basin_text}的水库有：{', '.join(names)}。"


def answer_question(question: str) -> Dict[str, str]:
    # 总流程：识别水库 -> 关系问答 -> 基础信息问答 -> 属性问答。
    question = question.strip()
    if not question:
        return {"answer": "请输入问题内容。", "source": "system"}

    def maybe_fallback(default_answer: str, reason: str) -> Dict[str, str]:
        llm_answer = ask_llm_fallback(question, context=reason)
        if llm_answer:
            return {"answer": llm_answer, "source": "llm"}
        return {"answer": default_answer, "source": "system"}

    # 1. 提取水库名
    reservoir = extract_reservoir_name(question)
    if not reservoir:
        suggestions = suggest_reservoir_names(question)
        if suggestions:
            default_answer = f"未识别到水库名称。你可能想问：{', '.join(suggestions)}。"
            return maybe_fallback(default_answer, "未识别到具体水库名称")
        return maybe_fallback("请指定一个水库名称，例如：小浪底水库、龙羊峡水库等。", "缺少水库名称")

    # 2-5 需要访问图数据库，统一做异常兜底。
    try:
        handlers = {
            "answer_same_basin_reservoirs_question": answer_same_basin_reservoirs_question,
            "answer_relation_question": answer_relation_question,
            "answer_basic_info_question": answer_basic_info_question,
        }
        for handler_name in ANSWER_HANDLER_NAMES:
            handler = handlers[handler_name]
            answer = handler(question, reservoir)
            if answer:
                return {"answer": answer, "source": "kg"}

        # 4. 提取要查询的属性
        attr_cn, attr_en = extract_attr(question)
        if not attr_en:
            supported_attrs = "、".join(ATTR_MAPPING.keys())
            default_answer = f"我暂时只能回答以下属性：{supported_attrs}。"
            return maybe_fallback(default_answer, "属性未命中规则映射")

        # 5. 从 Neo4j 中查询（注意参数化查询防止注入）
        result = _run_reservoir_query(
            reservoir,
            "RETURN r[$attr] AS value LIMIT 1",
            {"attr": attr_en},
        )
    except HTTPException:
        return {"answer": SERVICE_UNAVAILABLE_MSG, "source": "system"}

    if result and result[0]["value"] is not None:
        value = result[0]["value"]
        # 根据属性类型添加单位
        unit = UNIT_MAPPING.get(attr_en)
        if unit:
            return {"answer": f"{reservoir}的{attr_cn}是{value}{unit}。", "source": "kg"}
        return {"answer": f"{reservoir}的{attr_cn}是{value}。", "source": "kg"}
    default_answer = f"未找到{reservoir}的{attr_cn}信息。"
    return maybe_fallback(default_answer, "图谱中未找到对应属性值")

