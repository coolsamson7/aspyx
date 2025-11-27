from abc import ABC, abstractmethod
from typing import Optional, Callable, Any
from datetime import datetime, timezone

from aspyx.di import injectable

from .session import Session
from .session_context import SessionContext

@injectable()
class SessionManager(SessionContext):
    """
    A SessionManager controls the lifecycle of sessions and is responsible to establish a session context local.
    """

    # local classes

    class Storage(ABC):
        @abstractmethod
        def store(self, token: str, session: Session, ttl_seconds: int):
            pass

        @abstractmethod
        def read(self, token: str) -> Optional[Session]:
            pass

    # constructor

    def __init__(self, storage: 'SessionManager.Storage'):
        self.storage = storage
        self.session_factory : Optional[Callable[[Any], Session]] = None

    # public

    def set_factory(self, factory: Callable[..., Session]) -> None:
        """
        set a factory function that will be used to create a concrete session
        Args:
            factory: the function
        """
        self.session_factory = factory

    def create_session(self, *args, **kwargs) -> Session:
        """
        create a session given the arguments (usually a token, etc.)
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

        self.storage.store(token, session, ttl_seconds)

    def read_session(self, token: str) -> Optional[Session]:
        return self.storage.read(token)
