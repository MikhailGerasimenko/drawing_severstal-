import os

from dotenv import load_dotenv
from openai import OpenAI
from openai import APIConnectionError, APITimeoutError

from .prompting import SYSTEM_PROMPT, build_user_prompt


class QwenPassportGenerator:
    def __init__(self) -> None:
        load_dotenv()
        provider = os.getenv("LLM_PROVIDER", "").strip().lower()

        if not provider:
            provider = "openrouter" if os.getenv("OPENROUTER_API_KEY") else "qwen"

        self.provider = provider
        self.model = ""
        self.client = None

        if provider == "openrouter":
            api_key = os.getenv("OPENROUTER_API_KEY")
            base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
            model = os.getenv("OPENROUTER_MODEL", "qwen/qwen-2.5-72b-instruct")
            site_url = os.getenv("OPENROUTER_SITE_URL", "")
            app_name = os.getenv("OPENROUTER_APP_NAME", "dxf-passport-builder")

            if api_key:
                headers = {"X-Title": app_name}
                if site_url:
                    headers["HTTP-Referer"] = site_url
                self.client = OpenAI(
                    api_key=api_key,
                    base_url=base_url,
                    default_headers=headers,
                    max_retries=0,
                    timeout=30,
                )
                self.model = model
        else:
            api_key = os.getenv("QWEN_API_KEY")
            base_url = os.getenv(
                "QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
            )
            model = os.getenv("QWEN_MODEL", "qwen-plus")

            if api_key:
                self.client = OpenAI(api_key=api_key, base_url=base_url, max_retries=0, timeout=30)
                self.model = model

    def generate(self, normalized_drawing, reference_text: str) -> str:
        if not self.client:
            return self._fallback_markdown(normalized_drawing)

        prompt = build_user_prompt(normalized_drawing, reference_text)
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                timeout=60,
            )
            return completion.choices[0].message.content or self._fallback_markdown(normalized_drawing)
        except (APITimeoutError, APIConnectionError):
            return self._fallback_markdown(normalized_drawing)
        except Exception:
            return self._fallback_markdown(normalized_drawing)

    @staticmethod
    def _fallback_markdown(normalized) -> str:
        semantic = normalized.semantic_candidates
        designation = semantic.get("designation", {}).get("value", "Не указано в чертеже")
        title = semantic.get("product_name", {}).get("value", "Не указано в чертеже")
        dims = semantic.get("overall_dimensions", {}).get("value", "Не указано в чертеже")
        return f"""# Паспорт изделия

## 1. ОБЩИЕ ДАННЫЕ
- Тип: {title}
- Обозначение: {designation}
- Габариты (Макс): {dims}
- Материал/Твердость: {semantic.get("material_hardness", {}).get("value", "Не указано в чертеже")}

## 2. ГЕОМЕТРИЯ (ЧИСТОВАЯ)
- Основные размеры: {normalized.drawing_facts.get("dimensions", [])[:15] if normalized.drawing_facts.get("dimensions") else "Не указано в чертеже"}
- Геометрические элементы: {normalized.drawing_facts.get("entity_counts", {})}
- Дополнительные элементы: Не указано в чертеже

## 3. ГДТ
- {semantic.get("gdt_facts", ["Не указано в чертеже"])[0] if semantic.get("gdt_facts") else "Не указано в чертеже"}

## 4. ПРИМЕЧАНИЯ
- Паспорт сформирован в режиме fallback (LLM API недоступен или вернул ошибку).
- Проверьте переменные провайдера (Qwen/OpenRouter) и доступность сервера.
"""
