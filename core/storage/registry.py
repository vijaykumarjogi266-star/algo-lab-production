from typing import Any


class Registry:
    """Simple in-memory registry for Algo Lab domain objects."""

    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}

    def add(self, item: Any) -> None:
        item_id = getattr(item, "id", None)

        if not item_id:
            raise ValueError("Registered objects must have an id.")

        if item_id in self._items:
            raise ValueError(f"Object already exists: {item_id}")

        self._items[item_id] = {
            "object": item,
            "type": type(item).__name__,
        }

    def get(self, item_id: str) -> Any:
        if item_id not in self._items:
            raise KeyError(f"Object not found: {item_id}")

        return self._items[item_id]["object"]

    def exists(self, item_id: str) -> bool:
        return item_id in self._items

    def count(self) -> int:
        return len(self._items)
