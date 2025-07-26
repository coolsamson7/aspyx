from typing import TypeVar, Generic, Optional, Callable

K = TypeVar("K")
V = TypeVar("V")

class CopyOnWriteCache(Generic[K, V]):
    """
    cache, that clones the existing dict, whenever a new item is added, avoiding any locks
    """
    # constructor

    def __init__(self, factory: Optional[Callable[[K], V]] = None) -> None:
        self._cache: dict[K, V] = {}
        self._factory = factory

    # public

    def get(self, key: K, factory: Optional[Callable[[K], V]] = None) -> Optional[V]:
        value = self._cache.get(key, None)
        if value is None:
            if factory is not None:
                value = factory(key)
                self.put(key, value)

            elif self._factory is not None:
                value = self._factory(key)
                self.put(key, value)

        return value

    def put(self, key: K, value: V) -> None:
        new_cache = self._cache.copy()
        new_cache[key] = value
        self._cache = new_cache

    def contains(self, key: K) -> bool:
        return key in self._cache

    def clear(self) -> None:
        self._cache = {}