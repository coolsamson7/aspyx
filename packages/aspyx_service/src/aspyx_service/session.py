"""
session related module
"""
from abc import ABC, abstractmethod
import contextvars
from typing import Type, Optional, Callable, Any, TypeVar
from datetime import datetime, timezone, timedelta
from cachetools import TTLCache

from aspyx.di import injectable


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

    # local classes

    class Storage(ABC):
        @abstractmethod
        def put(self, token: str, session: Session, ttl_seconds: int):
            pass

        @abstractmethod
        def get(self, token: str) -> Optional[Session]:
            pass

    class InMemoryStorage(Storage):
        """
        InMemoryStorage is a simple in-memory storage for sessions.
        It uses a TTLCache to store sessions with a time-to-live.
        """
        # constructor

        def __init__(self, max_size = 1000, ttl = 3600):
            self.cache = TTLCache(maxsize=max_size, ttl=ttl)

        # implement

        def put(self, token: str, session: 'Session', ttl_seconds: int):
            expiry_time = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
            self.cache[token] = (session, expiry_time)

        def get(self, token: str) -> Optional['Session']:
            value = self.cache.get(token)
            if value is None:
                return None

            session, expiry = value
            if expiry < datetime.now(timezone.utc):
                del self.cache[token]
                return None

            return session

    # class properties

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

    def __init__(self, storage: 'SessionManager.Storage'):
        self.storage = storage
        self.session_factory : Optional[Callable[[Any], Session]] = None

    # public

    def set_session_factory(self, factory: Callable[..., Session]) -> None:
        """
        set a factory function that will be used to create a concrete session
        Args:
            factory: the function
        """
        self.session_factory = factory

    def create_session(self, *args, **kwargs) -> Session:
        """
        create a session given the argument s(usually a token, etc.)
        Args:
            args: rest args
            kwargs: keyword args

        Returns:
            the new session
        """
        return self.session_factory(*args, **kwargs)

    def store_session(self, token: str, session: Session, expiry: datetime):
        now = datetime.now(timezone.utc)
        ttl_seconds = max(int((expiry - now).total_seconds()), 0)

        self.storage.put(token, session, ttl_seconds)

    def get_session(self, token: str) -> Optional[Session]:
        return self.storage.get(token)
