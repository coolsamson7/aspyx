"""
session related module
"""
import contextvars
from typing import Type, Optional, Callable, Any, TypeVar
from datetime import datetime, timezone
from cachetools import TTLCache

from aspyx.di import injectable
from aspyx.threading import ThreadLocal


class Session:
    """
    Base class for objects covers data related to a server side session.
    """
    def __init__(self):
        pass

T = TypeVar("T")

@injectable()
class SessionManager:
    """
    A SessionManager controls the lifecycle of sessions and is responsible to establish a session thread local.
    """
    #current_session = ThreadLocal[Session]()
    current_session  = contextvars.ContextVar("session")

    @classmethod
    def current(cls, type: Type[T]) -> T:
        """
        return the current session associated with the thread
        Args:
            type:  the session type

        Returns:
            the current session
        """
        return cls.current_session.get()

    @classmethod
    def set_session(cls, session: Session) -> None:
        """
        set the current session in the thread context
        Args:
            session: the session
        """
        cls.current_session.set(session)

    @classmethod
    def delete_session(cls) -> None:
        """
        delete the current session
        """
        cls.current_session.set(None)#clear()

    # constructor

    def __init__(self):
        self.sessions = TTLCache(maxsize=1000, ttl=3600)
        self.session_creator : Optional[Callable[[Any], Session]] = None

    # public

    def set_session_factory(self, callable: Callable[..., Session]) -> None:
        """
        set a factory function that will be used to create a concrete session
        Args:
            callable: the function
        """
        self.session_creator = callable

    def create_session(self, *args, **kwargs) -> Session:
        """
        create a session given the argument s(usually a token, etc.)
        Args:
            args: rest args
            kwargs: keyword args

        Returns:
            the new session
        """
        return self.session_creator(*args, **kwargs)

    def store_session(self, token: str, session: Session, expiry: datetime):
        now = datetime.now(timezone.utc)
        ttl_seconds = max(int((expiry - now).total_seconds()), 0)
        self.sessions[token] = (session, ttl_seconds)

    def get_session(self, token: str) -> Optional[Session]:
        value = self.sessions.get(token)
        if value is None:
            return None

        session, ttl = value
        return session
