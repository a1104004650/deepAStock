"""统一 LLM 调用接口 - 兼容 OpenAI / DeepSeek / 通义 / 智谱 / Ollama / Gemini / Claude"""
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
    """统一LLM调用接口：OpenAI / DeepSeek / 通义 / 智谱 / Ollama 本地 / Gemini / Claude"""

    def __init__(
        self,
        api_base: str = DEFAULT_API_BASE,
        api_key: str = "",
        model: str = "deepseek-chat",
        temperature: float = 0.3,
        max_tokens: int = 4000,
        timeout: int = 90,
        provider: str = "",
    ):
        self.api_base = (api_base or DEFAULT_API_BASE).rstrip("/")
        self.api_key = api_key or ""
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        base_l = self.api_base.lower()
        model_l = (model or "").lower()
        inferred = "openai"
        if "gemini" in (model_l) or "generativelanguage" in base_l:
            inferred = "gemini"
        elif "claude" in model_l or "anthropic" in base_l:
            inferred = "claude"
        elif "ollama" in base_l:
            inferred = "ollama"
        elif "deepseek" in base_l or "deepseek" in model_l:
            inferred = "deepseek"
        elif "dashscope" in base_l or "qwen" in model_l or "tongyi" in base_l:
            inferred = "qwen"
        elif "openai" in base_l or "api.x.ai" in base_l:
            inferred = "openai"
        elif "zhipu" in base_l or "bigmodel" in base_l:
            inferred = "zhipu"
        self.provider = provider or inferred

    async def complete(self, prompt: str, system_prompt: str = "", response_format: str = "text") -> str:
        if not self.api_key and self.provider != "ollama":
            raise LLMNotConfigured("未配置 API Key，已切换本地启发式分析")

        if self.provider == "gemini":
            return await self._complete_gemini(prompt, system_prompt, response_format)
        if self.provider == "claude":
            return await self._complete_claude(prompt, system_prompt, response_format)
        return await self._complete_openai(prompt, system_prompt, response_format)

    async def stream_complete(self, prompt: str, system_prompt: str = ""):
        """流式输出 LLM tokens，yield 文本片段。Gemini/Claude 降级为一次性返回。"""
        if self.provider in ("gemini", "claude"):
            full = await self.complete(prompt, system_prompt)
            yield full
            return

        if not self.api_key and self.provider != "ollama":
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
            "stream": True,
        }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.provider == "ollama":
            headers.pop("Authorization", None)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", f"{self.api_base}/chat/completions",
                                         headers=headers, json=payload) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise LLMError(f"API error {resp.status_code}: {body[:300]}")
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            choices = data.get("choices", [])
                            if choices:
                                token = choices[0].get("delta", {}).get("content", "")
                                if token:
                                    yield token
                        except json.JSONDecodeError:
                            continue
        except httpx.ConnectError as e:
            raise LLMError(f"LLM 连接失败: {e}") from e

    async def _complete_openai(self, prompt: str, system_prompt: str = "", response_format: str = "text") -> str:
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

        # Ollama 不需要 Authorization，也不需要 json_object
        if self.provider == "ollama":
            headers.pop("Authorization", None)
            payload.pop("response_format", None)

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
            if self.provider == "ollama" and "message" in data:
                return data["message"]["content"]
            return data["choices"][0]["message"]["content"]
        except httpx.ConnectError as e:
            raise LLMError(f"LLM 连接失败: {e}") from e

    async def _complete_gemini(self, prompt: str, system_prompt: str = "", response_format: str = "text") -> str:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
            },
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        url = (f"{self.api_base}/models/{self.model}:generateContent"
               + ("?key=" + self.api_key if self.api_key else ""))
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload,
                                         headers={"Content-Type": "application/json"})
            if resp.status_code != 200:
                raise LLMError(f"Gemini error {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except httpx.ConnectError as e:
            raise LLMError(f"Gemini 连接失败: {e}") from e

    async def _complete_claude(self, prompt: str, system_prompt: str = "", response_format: str = "text") -> str:
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            payload["system"] = system_prompt
        headers = {"Content-Type": "application/json",
                   "x-api-key": self.api_key,
                   "anthropic-version": "2023-06-01"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.api_base}/v1/messages", headers=headers, json=payload)
            if resp.status_code != 200:
                raise LLMError(f"Claude error {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            return "".join(b.get("text", "") for b in data.get("content", []))
        except httpx.ConnectError as e:
            raise LLMError(f"Claude 连接失败: {e}") from e

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