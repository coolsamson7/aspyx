"""
context utility
"""
import contextvars
from contextlib import contextmanager
from typing import Generic, Optional, TypeVar, Any

T = TypeVar("T")

class ContextLocal(Generic[T]):
    """
    A context local value holder
    """
    # constructor

    def __init__(self, name: str, default: Optional[T] = None):
        self.var = contextvars.ContextVar(name, default=default)

    # public

    def get(self) -> Optional[T]:
        """
        return the current value or invoke the optional factory to compute one

        Returns:
            Optional[T]: the value associated with the current thread
        """
        return self.var.get()

    def set(self, value: Optional[T]) -> Any:
        """
        set a value in the current thread

        Args:
            value: the value

        Returns:
            a token that can be used as an argument to `reset`
        """
        return self.var.set(value)

    def reset(self, token) -> None:
        """
        clear the value in the current thread

        Args:
            token: the token to clear
        """
        self.var.reset(token)

    @contextmanager
    def use(self, value):
        token = self.set(value)
        try:
            yield
        finally:
            self.reset(token)
