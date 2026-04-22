from typing import Any, Optional

from config import get_settings

SYSTEM_PROMPT = (
    "你是水资源知识助手。"
    "当上下文不足时请明确说明不确定，避免编造。"
)


def ask_llm_fallback(question: str, context: str = "") -> Optional[str]:
    settings = get_settings()
    if not settings.llm_enabled:
        return None
    if settings.llm_backend != "cloud":
        return None
    if not settings.llm_api_key:
        return None

    try:
        from openai import OpenAI
        import logging
        logger = logging.getLogger("qa_llm_service")
    except Exception:
        return None

    try:
        client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url or None,
            timeout=settings.llm_timeout_seconds,
        )
        messages: Any = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"问题：{question}\n上下文：{context}",
            },
        ]
        response = client.chat.completions.create(
            model=settings.llm_model,
            temperature=0.2,
            messages=messages,
        )
        content = response.choices[0].message.content
        if not content:
            return None
        answer = content.strip()
        return answer or None
    except Exception as e:
        logger.error(f"LLM fallback request failed: {e}")
        return None

