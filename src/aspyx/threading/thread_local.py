"""
Some threading related utilities.
"""

import threading

from typing import Callable, Optional, TypeVar, Generic

T = TypeVar("T")
class ThreadLocal(Generic[T]):
    """
    A thread local value holder
    """
    # constructor

    def __init__(self, default_factory: Optional[Callable[[], T]] = None):
        self.local = threading.local()
        self.factory = default_factory

    # public

    def get(self) -> Optional[T]:
        if not hasattr(self.local, "value"):
            if self.factory is not None:
                self.local.value = self.factory()
            else:
                return None

        return self.local.value

    def set(self, value: T) -> None:
        self.local.value = value

    def clear(self) -> None:
        if hasattr(self.local, "value"):
            del self.local.value
