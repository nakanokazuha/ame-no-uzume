import json
from pathlib import Path

from pydantic import TypeAdapter

from yume_api.contracts.events import WorldEvent


def main() -> None:
    output = Path("packages/contracts/schemas/world-event.schema.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(TypeAdapter(WorldEvent).json_schema(), indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
