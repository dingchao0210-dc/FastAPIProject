from typing import Any, Dict, List

import qa_service


def test_extract_attr_matches_long_keyword_first() -> None:
    cn, en = qa_service.extract_attr("某水库装机容量是多少")
    assert cn == "装机容量"
    assert en == "installed_capacity"


def test_extract_reservoir_name_from_dynamic_alias() -> None:
    original = qa_service.load_dynamic_reservoir_aliases
    qa_service.load_dynamic_reservoir_aliases = lambda: {"龙羊峡": "龙羊峡水库", "龙羊峡水库": "龙羊峡水库"}  # type: ignore[assignment]
    try:
        name = qa_service.extract_reservoir_name("龙羊峡的坝高")
        assert name == "龙羊峡水库"
    finally:
        qa_service.load_dynamic_reservoir_aliases = original  # type: ignore[assignment]


def test_answer_same_basin_reservoirs_question() -> None:
    def fake_run_cypher(_: str, __: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [{"basin": "黄河流域", "reservoirs": ["龙羊峡水库", "刘家峡水库", "小浪底水库"]}]

    original = qa_service.run_cypher
    qa_service.run_cypher = fake_run_cypher  # type: ignore[assignment]
    try:
        answer = qa_service.answer_same_basin_reservoirs_question("龙羊峡水库相同流域上的所有水库有哪些", "龙羊峡水库")
        assert answer == "与龙羊峡水库同属黄河流域的水库有：刘家峡水库, 小浪底水库。"
    finally:
        qa_service.run_cypher = original  # type: ignore[assignment]


def test_answer_question_uses_llm_fallback_when_attr_unmatched() -> None:
    original_extract_name = qa_service.extract_reservoir_name
    original_ask_llm = qa_service.ask_llm_fallback
    qa_service.extract_reservoir_name = lambda _: "龙羊峡水库"  # type: ignore[assignment]
    qa_service.ask_llm_fallback = lambda _q, context="": f"LLM:{context}"  # type: ignore[assignment]
    try:
        answer = qa_service.answer_question("龙羊峡水库今天安全吗")
        assert answer["answer"] == "LLM:属性未命中规则映射"
        assert answer["source"] == "llm"
    finally:
        qa_service.extract_reservoir_name = original_extract_name  # type: ignore[assignment]
        qa_service.ask_llm_fallback = original_ask_llm  # type: ignore[assignment]


def test_answer_question_prefers_rule_answer_over_llm() -> None:
    original_extract_name = qa_service.extract_reservoir_name
    original_ask_llm = qa_service.ask_llm_fallback
    original_run_cypher = qa_service.run_cypher
    qa_service.extract_reservoir_name = lambda _: "龙羊峡水库"  # type: ignore[assignment]
    qa_service.ask_llm_fallback = lambda _q, context="": "不应命中"  # type: ignore[assignment]

    def fake_run_cypher(_: str, __: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [{"value": 178}]

    qa_service.run_cypher = fake_run_cypher  # type: ignore[assignment]
    try:
        answer = qa_service.answer_question("龙羊峡水库的坝高是多少")
        assert answer["answer"] == "龙羊峡水库的坝高是178米。"
        assert answer["source"] == "kg"
    finally:
        qa_service.extract_reservoir_name = original_extract_name  # type: ignore[assignment]
        qa_service.ask_llm_fallback = original_ask_llm  # type: ignore[assignment]
        qa_service.run_cypher = original_run_cypher  # type: ignore[assignment]

