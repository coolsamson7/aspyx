from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional, Type

from sqlalchemy.orm import Session, DeclarativeBase

from aspyx.di import injectable
from aspyx.di.aop import around, advice, methods, classes, Invocation
from aspyx.reflection import Decorators

from .persistent_unit import PersistentUnit

def transactional(persistent_unit : Optional[Type[PersistentUnit]] = None):
    def decorator(func):
        Decorators.add(func, transactional, persistent_unit)
        return func #

    return decorator


_current_session: ContextVar[Session] = ContextVar("_current_session", default=None)

def get_current_session():
    return _current_session.get()

@advice
@injectable()
class TransactionalAdvice:
    # internal

    def get_persistent_unit(self, invocation: Invocation):
        tx = Decorators.get_decorator(invocation.func, transactional)
        if tx is None:
            tx = Decorators.get_decorator(type(invocation.args[0]), transactional)

        declarative_base = tx.args[0]

        return PersistentUnit.get_persistent_unit(declarative_base)

    # advice

    @around(methods().decorated_with(transactional), classes().decorated_with(transactional))
    def call_transactional(self, invocation: Invocation):
        outer = _current_session.get()
        if outer is not None:
            return invocation.proceed()

        persistent_unit = self.get_persistent_unit(invocation)

        session = persistent_unit.create_session()

        #session = self.session_factory.create_session()
        token = _current_session.set(session)

        try:
            result = invocation.proceed()
            session.flush()
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            _current_session.reset(token)

@contextmanager
def transaction(base : Optional[Type[DeclarativeBase]] = None):
    outer = _current_session.get()
    if outer is not None:
        yield
        return

    persistent_unit = PersistentUnit.get_persistent_unit(base)
    session = persistent_unit.create_session()
    token = _current_session.set(session)

    try:
        yield
        session.flush()
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        _current_session.reset(token)