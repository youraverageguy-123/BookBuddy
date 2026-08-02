from collections import OrderedDict
from threading import RLock
from typing import Generic, TypeVar

T = TypeVar("T")


class LRUCache(Generic[T]):
    def __init__(self, capacity: int = 512):
        self.capacity = max(1, int(capacity))
        self._items: OrderedDict[str, T] = OrderedDict()
        self._lock = RLock()

    def get(self, key: str):
        with self._lock:
            if key not in self._items:
                return None
            value = self._items.pop(key)
            self._items[key] = value
            return value

    def put(self, key: str, value: T) -> T:
        with self._lock:
            self._items.pop(key, None)
            self._items[key] = value
            while len(self._items) > self.capacity:
                self._items.popitem(last=False)
        return value
