import base64
import json
import logging
from typing import Any
from openai import OpenAI

from cores.config import API_KEY, DEFAULT_IMAGE_PROMPT,   EXTRACT_FROM_SCHEMA_PROMPT, LLM_BASEAPI, LLM_MODEL, MARKDOWN_TO_JSON_PROMPT
from cores.dbconnection.mongo import get_db
from utils.kvm_client import request_with_log


CONFIG_KEY = "system_settings"
logger = logging.getLogger("llm_client")


def _preview_text(value: str, limit: int = 800) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]..."


def _load_runtime_llm_settings() -> dict[str, str]:
    settings = {
        "llm_base_api": LLM_BASEAPI,
        "llm_model": LLM_MODEL,
        "api_key": API_KEY,
        "default_image_prompt": DEFAULT_IMAGE_PROMPT,
        "markdown_to_json_prompt": MARKDOWN_TO_JSON_PROMPT,
        "extract_from_schema_prompt": EXTRACT_FROM_SCHEMA_PROMPT,
    }
    try:
        db = get_db()
        doc = db.app_config.find_one({"_key": CONFIG_KEY}) or {}
        for key in settings:
            if key in doc and doc.get(key) is not None:
                settings[key] = doc[key]
    except Exception:
        pass
    return settings


def ensure_llm_name(markdown: str, fallback: str) -> str:
    lines = [line.strip() for line in markdown.splitlines() if line.strip()]
    for line in lines:
        if line.startswith("#"):
            return line.strip("# ")[:255]
    return fallback


def call_llm_image_to_markdown(image_bytes: bytes) -> str:
    settings = _load_runtime_llm_settings()
    if not settings["llm_base_api"]:
        return ""
    
    client = OpenAI(
        base_url=settings["llm_base_api"].rstrip("/") + "/v1",
        api_key=settings["api_key"] or "no-key"
    )

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    
    try:
        response = client.chat.completions.create(
            model=settings["llm_model"],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": settings["default_image_prompt"]},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    ],
                }
            ],
            temperature=0,
            timeout=600
        )
        content = response.choices[0].message.content.strip()
        logger.info("LLM markdown output (%d chars):\n%s", len(content), _preview_text(content))
        return content
    except Exception as exc:
        logger.exception("image->markdown failed: %s", exc)
        return ""

def _extract_entities_from_openai_response(response) -> dict[str, Any]:
    try:
        content = response.choices[0].message.content.strip()
        logger.info("LLM raw JSON output (%d chars):\n%s", len(content), _preview_text(content))
        
        # Clean markdown fences
        if content.startswith("```"):
            content = content.strip("`")
            if content.startswith("json"):
                content = content[4:].strip()
                
        start_idx = content.find('{')
        end_idx = content.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            content = content[start_idx:end_idx+1]
            
        parsed = json.loads(content)
        if "entities" not in parsed or not isinstance(parsed["entities"], list):
            parsed["entities"] = []
        parsed["_raw_response"] = content
        parsed["_parse_error"] = None
        return parsed
    except Exception as exc:
        logger.exception("JSON parse failed: %s", exc)
        return {"entities": [], "_parse_error": str(exc)}

    
def call_llm_markdown_to_json(markdown: str, image_bytes: bytes | None = None, promptype='markdown_to_json_prompt', schema_str: str | None = None) -> dict[str, Any]:
    settings = _load_runtime_llm_settings()
    if not settings["llm_base_api"]:
        return {"screen_title": "", "entities": []}
    
    client = OpenAI(
        base_url=settings["llm_base_api"].rstrip("/") + "/v1",
        api_key=settings["api_key"] or "no-key"
    )

    if image_bytes:
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        user_content = [
            {"type": "text", "text": f"MARKDOWN CONTENT:\n{markdown}" if markdown else "Please extract from image based on the schema below."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
        ]
        if schema_str:
            user_content.insert(0, {"type": "text", "text": f"REQUIRED SCHEMA:\n{schema_str}"})
    else:
        user_content = f"REQUIRED SCHEMA:\n{schema_str}\n\n{markdown}" if schema_str else markdown

    try:
        response = client.chat.completions.create(
            model=settings["llm_model"],
            messages=[
                {"role": "system", "content": settings[promptype]},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            timeout=600
        )
        return _extract_entities_from_openai_response(response)
    except Exception as exc:
        logger.error("markdown->json failed: %s", exc)
        return {"entities": [], "_parse_error": str(exc)}



