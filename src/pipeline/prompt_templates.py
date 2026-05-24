import json
from pathlib import Path
from typing import Any


def render_template(template: str, values: dict[str, Any]) -> str:
    rendered = template
    for key, value in values.items():
        if isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False, indent=2)
        else:
            text = "" if value is None else str(value)
        rendered = rendered.replace(f"{{{{{key}}}}}", text)
    return rendered.strip()


def render_prompt_file(path: str, values: dict[str, Any]) -> str:
    template = Path(path).read_text(encoding="utf-8")
    return render_template(template, values)
