import contextvars

from typing import Type, TypeVar
from.session import Session

T = TypeVar("T")

class SessionContext:
    # class properties

    # current_session = ThreadLocal[Session]()
    current_session = contextvars.ContextVar("session")

    @classmethod
    def get(cls, type: Type[T]) -> T:
        """
        return the current session associated with the context
        Args:
            type:  the session type

        Returns:
            the current session
        """
        return cls.current_session.get()

    @classmethod
    def set(cls, session: Session) -> None:
        """
        set the current session in the context
        Args:
            session: the session
        """
        cls.current_session.set(session)

    @classmethod
    def clear(cls) -> None:
        """
        delete the current session
        """
        cls.current_session.set(None)  # clear()