"""统一 LLM 调用接口 - 兼容 OpenAI 格式"""
import json
import re
import time
import httpx
from app.utils.logger import logger

DEFAULT_API_BASE = "https://api.deepseek.com/v1"


class LLMError(Exception):
    pass


class LLMNotConfigured(LLMError):
    """未配置 API Key，走本地启发式分析"""


class LLMClient:
    """统一LLM调用接口：OpenAI / DeepSeek / 通义 / 智谱 / Ollama 本地"""

    def __init__(
        self,
        api_base: str = DEFAULT_API_BASE,
        api_key: str = "",
        model: str = "deepseek-chat",
        temperature: float = 0.3,
        max_tokens: int = 4000,
        timeout: int = 90,
    ):
        self.api_base = (api_base or DEFAULT_API_BASE).rstrip("/")
        self.api_key = api_key or ""
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    async def complete(self, prompt: str, system_prompt: str = "", response_format: str = "text") -> str:
        if not self.api_key:
            raise LLMNotConfigured("未配置 API Key，已切换本地启发式分析")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.api_base}/chat/completions",
                    headers=headers,
                    json=payload,
                )
            if resp.status_code != 200:
                raise LLMError(f"API error {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except httpx.ConnectError as e:
            raise LLMError(f"LLM 连接失败: {e}") from e

    async def complete_json(self, prompt: str, system_prompt: str = "") -> dict:
        raw = ""
        try:
            raw = await self.complete(prompt, system_prompt, response_format="json")
            return json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
            if m:
                return json.loads(m.group(1))
            m2 = re.search(r"\{.*\}", raw, re.DOTALL)
            if m2:
                return json.loads(m2.group(0))
            raise LLMError(f"LLM返回无法解析为JSON: {raw[:200]}")