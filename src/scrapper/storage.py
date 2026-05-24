import json
import math
from pathlib import Path
from typing import Any


RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")


def to_json_safe(value: Any) -> Any:
    if isinstance(value, float) and math.isnan(value):
        return None

    if isinstance(value, dict):
        return {key: to_json_safe(item) for key, item in value.items()}

    if isinstance(value, list):
        return [to_json_safe(item) for item in value]

    return value


def save_json(data: list[dict] | dict, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(to_json_safe(data), file, indent=2, ensure_ascii=False)

    return output_path
