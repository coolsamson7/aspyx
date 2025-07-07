"""
session stuff
"""
import contextvars
from typing import Type, Optional, Callable, Any, TypeVar
from datetime import datetime, timezone
from cachetools import TTLCache

from aspyx.di import injectable
#from aspyx.threading import ThreadLocal


class Session:
    def __init__(self):
        pass

T = TypeVar("T")

@injectable()
class SessionManager:
    #current_session = ThreadLocal[Session]()
    current_session  = contextvars.ContextVar("session")

    @classmethod
    def current(cls, type: Type[T]) -> T:
        return cls.current_session.get()

    @classmethod
    def set_session(cls, session: Session):
        cls.current_session.set(session)

    @classmethod
    def delete_session(cls):
        cls.current_session.set(None)#clear()

    # constructor

    def __init__(self):
        self.sessions = TTLCache(maxsize=1000, ttl=3600)
        self.session_creator : Optional[Callable[[Any], Session]] = None

    # public

    def set_session_creator(self, callable: Callable[[Any], Session]):
        self.session_creator = callable

    def create_session(self, jwt: Any) -> Session:
        return self.session_creator(jwt)

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
