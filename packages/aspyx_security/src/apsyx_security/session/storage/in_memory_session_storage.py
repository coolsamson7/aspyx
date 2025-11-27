from typing import Optional

from cachetools import TTLCache
from datetime import datetime, timezone, timedelta
from ..session import Session
from ..session_manager import SessionManager

class InMemoryStorage(SessionManager.Storage):
        """
        InMemoryStorage is a simple in-memory storage for sessions.
        It uses a TTLCache to store sessions with a time-to-live.
        """
        # constructor

        def __init__(self, max_size = 1000, ttl = 3600):
            self.cache = TTLCache(maxsize=max_size, ttl=ttl)

        # implement

        def store(self, token: str, session: Session, ttl_seconds: int):
            expiry_time = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
            self.cache[token] = (session, expiry_time)

        def read(self, token: str) -> Optional[Session]:
            value = self.cache.get(token)
            if value is None:
                return None

            session, expiry = value
            if expiry < datetime.now(timezone.utc):
                del self.cache[token]
                return None

            return session