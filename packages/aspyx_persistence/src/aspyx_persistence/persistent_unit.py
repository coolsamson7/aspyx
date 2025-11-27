from __future__ import annotations

from typing import Dict, Optional, Type

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session


class PersistentUnit:
    # static

    units : Dict[Type[DeclarativeBase], "PersistentUnit"] = {}

    @staticmethod
    def get_persistent_unit(base : Optional[Type[DeclarativeBase]]):
        if base is not None:
            return PersistentUnit.units[base]
        else:
            return next(iter(PersistentUnit.units.values()))

    @staticmethod
    def create_session_for(base : Type[DeclarativeBase]):
        return PersistentUnit.units[base].create_session()

    # constructor

    def __init__(self, url: str, declarative_base: Type[DeclarativeBase]):
        self.url = url
        self.declarative_base = declarative_base
        self.engine = create_engine(url, echo=False, future=True)
        self._maker = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

        PersistentUnit.units[declarative_base] = self

    # public

    def create_all(self):
        """
        Creates all tables for the associated DeclarativeBase.
        Equivalent to Base.metadata.create_all(engine)
        """
        self.declarative_base.metadata.create_all(self.engine)

    def create_session(self) -> Session:
        return self._maker()