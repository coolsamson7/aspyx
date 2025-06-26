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
        """
        return the current value or invoke the optional factory to compute one

        Returns:
            Optional[T]: the value associated with the current thread
        """
        if not hasattr(self.local, "value"):
            if self.factory is not None:
                self.local.value = self.factory()
            else:
                return None

        return self.local.value

    def set(self, value: T) -> None:
        """
        set a value in the current thread

        Args:
            value: the value
        """
        self.local.value = value

    def clear(self) -> None:
        """
        clear the value in the current thread
        """
        if hasattr(self.local, "value"):
            del self.local.value
