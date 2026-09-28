import os
import re
import json
import hashlib
from typing import List, Dict, Optional, Tuple, Any, Union
import requests


class LLMEngine:
    """
    Multi-provider LLM Engine for Syllabus Extraction:
    - Supports Google Gemini, OpenAI, Anthropic, Groq, DeepSeek, OpenRouter, and Local Ollama.
    - Uses SHA-256 persistent disk + memory caching for 100% determinism and zero duplicate calls.
    - Used for variable layout boundary identification (returning line ranges) and complex section parsing.
    - Gracefully falls back to deterministic rule heuristics if no API key or provider is available.
    """

    CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", ".cache")
    CACHE_FILE = os.path.join(CACHE_DIR, "llm_cache.json")

    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        self.provider = (provider or os.environ.get("LLM_PROVIDER") or self._detect_provider()).lower()
        self.api_key = api_key or self._detect_api_key(self.provider)
        self.model = model or os.environ.get("LLM_MODEL") or self._default_model(self.provider)
        self.base_url = base_url or os.environ.get("LLM_BASE_URL") or self._default_base_url(self.provider)
        self.cache: Dict[str, Any] = self._load_cache()

    def _detect_provider(self) -> str:
        if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            return "gemini"
        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "anthropic"
        if os.environ.get("GROQ_API_KEY"):
            return "groq"
        if os.environ.get("DEEPSEEK_API_KEY"):
            return "deepseek"
        if os.environ.get("OLLAMA_HOST"):
            try:
                res = requests.get(f"{os.environ.get('OLLAMA_HOST')}/api/tags", timeout=0.1)
                if res.status_code == 200:
                    return "ollama"
            except Exception:
                pass
        return "heuristic"

    def _detect_api_key(self, provider: str) -> Optional[str]:
        if provider == "gemini":
            return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if provider == "openai":
            return os.environ.get("OPENAI_API_KEY")
        if provider == "anthropic":
            return os.environ.get("ANTHROPIC_API_KEY")
        if provider == "groq":
            return os.environ.get("GROQ_API_KEY")
        if provider == "deepseek":
            return os.environ.get("DEEPSEEK_API_KEY")
        return os.environ.get("LLM_API_KEY")

    def _default_model(self, provider: str) -> str:
        if provider == "gemini":
            return "gemini-1.5-flash"  # Ultra-lightweight & fast
        if provider == "openai":
            return "gpt-4o-mini"        # Lightweight mini model
        if provider == "anthropic":
            return "claude-3-haiku-20240307"  # Lightweight haiku
        if provider == "groq":
            return "llama-3.1-8b-instant"     # Lightweight 8B instant model
        if provider == "deepseek":
            return "deepseek-chat"
        if provider == "ollama":
            return "llama3.2"                 # Low-resource local model (1B/3B)
        return "heuristic-engine"

    def _default_base_url(self, provider: str) -> str:
        if provider == "ollama":
            return os.environ.get("OLLAMA_HOST") or "http://localhost:11434"
        if provider == "groq":
            return "https://api.groq.com/openai/v1"
        if provider == "deepseek":
            return "https://api.deepseek.com/v1"
        return ""

    def _load_cache(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.CACHE_FILE):
                with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_cache(self):
        try:
            os.makedirs(self.CACHE_DIR, exist_ok=True)
            with open(self.CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get_hash(self, prompt: str, text: str) -> str:
        payload = f"{self.provider}:{self.model}:{prompt}\n---\n{text}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> Optional[str]:
        """
        Queries LLM with SHA-256 caching and temperature=0 for determinism.
        """
        req_hash = self.get_hash(system_prompt, user_prompt)
        if req_hash in self.cache:
            return self.cache[req_hash]

        if not self.api_key and self.provider != "ollama":
            return None

        response_text = None
        try:
            if self.provider == "gemini":
                response_text = self._call_gemini(system_prompt, user_prompt, temperature)
            elif self.provider in ["openai", "groq", "deepseek"]:
                response_text = self._call_openai_compatible(system_prompt, user_prompt, temperature)
            elif self.provider == "anthropic":
                response_text = self._call_anthropic(system_prompt, user_prompt, temperature)
            elif self.provider == "ollama":
                response_text = self._call_ollama(system_prompt, user_prompt, temperature)
        except Exception as e:
            response_text = None

        if response_text:
            self.cache[req_hash] = response_text
            self._save_cache()

        return response_text

    def _call_gemini(self, system_prompt: str, user_prompt: str, temperature: float) -> Optional[str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}
            ],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json"
            }
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
        return None

    def _call_openai_compatible(self, system_prompt: str, user_prompt: str, temperature: float) -> Optional[str]:
        base = self.base_url.rstrip("/") if self.base_url else "https://api.openai.com/v1"
        url = f"{base}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        payload = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "response_format": {"type": "json_object"}
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
        return None

    def _call_anthropic(self, system_prompt: str, user_prompt: str, temperature: float) -> Optional[str]:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}]
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            content = data.get("content", [])
            if content and content[0].get("type") == "text":
                return content[0].get("text", "")
        return None

    def _call_ollama(self, system_prompt: str, user_prompt: str, temperature: float) -> Optional[str]:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": temperature}
        }
        resp = requests.post(url, json=payload, timeout=45)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("response", "")
        return None
