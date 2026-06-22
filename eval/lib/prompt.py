from __future__ import annotations

import re
from pathlib import Path

DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[2] / "docs" / "system_prompt_passport_markdown.md"


def load_system_prompt(path: Path | None = None) -> str:
    source = path or DEFAULT_PROMPT_PATH
    text = source.read_text(encoding="utf-8")
    match = re.search(r"```text\s*\n(.*?)```", text, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()
