from __future__ import annotations

import re

from typing import Optional, Any, Callable, List
from typing import Generic, Type, TypeVar

from sqlalchemy.orm import declarative_base

from aspyx.mapper import Mapper
from aspyx.reflection import Decorators
from aspyx.di.aop import advice, Invocation, around, methods
from aspyx.di import injectable

from .transactional import _current_session

Base = declarative_base()

T = TypeVar("T")

def query():
    """
    Methods decorated with `@query` are queries.
    """
    def decorator(func):
        Decorators.add(func, query)

        return func

    return decorator

class BaseRepository(Generic[T]):
    # instance data

    _query_cache: dict[str, Callable[..., Any]] = {}

    # constructor

    def __init__(self, model: Type[T]):
        self.model = model

    # internal

    def _invoke_dynamic_query(self, method_name: str, *args, **kwargs):
        cache_key = method_name
        if cache_key not in self._query_cache:
            # parse the method name
            self._query_cache[cache_key] = self._create_query_func(method_name)
        func = self._query_cache[cache_key]
        return func(self, *args, **kwargs)

    def _create_query_func(self, method_name: str) -> Callable[..., Any]:
        """
        Converts method names like find_by_name_and_locale into a query function.
        """
        m = re.match(r"find_by_(.+)", method_name)
        if not m:
            raise ValueError(f"Cannot parse method name {method_name}")
        fields = m.group(1).split("_and_")

        def query_func(instance: "BaseRepository", *args, **kwargs):
            if len(args) > 0:
                # map positional args to field names
                query_kwargs = dict(zip(fields, args))
            else:
                query_kwargs = kwargs
            return instance.filter(**query_kwargs)

        return query_func

    # public

    def get_current_session(self):
        return _current_session.get()

    # query stuff

    def find(self, id_, mapper: Optional[Mapper] = None) -> T | None:
        result = self.get_current_session().get(self.model, id_)
        if result is not None:
            return mapper.map(result) if mapper is not None else result

    def get(self, id_, mapper: Optional[Mapper] = None) -> T:
        result = self.get_current_session().get(self.model, id_)
        if result is not None:
            return mapper.map(result) if mapper is not None else result

    def find_all(self, mapper: Optional[Mapper] = None) -> List[T]:
        result = list(self.get_current_session().query(self.model))
        if mapper is None:
            return result
        else:
            return [mapper.map(entity) for entity in result]

    def save(self, entity: T) -> T:
        self.get_current_session().add(entity)

        return entity

    def delete(self, entity: T):
        self.get_current_session().delete(entity)

    def filter(self, **kwargs) -> list[T]:
        return self.get_current_session().query(self.model).filter_by(**kwargs).all()

    def exists(self, **kwargs) -> bool:
        return self.get_current_session().query(self.get_current_session().query(self.model)
                                                .filter_by(**kwargs)
                                                .exists()).scalar()

@advice
@injectable()
class QueryAdvice:
    # constructor

    def __init__(self):
        pass

    # advice

    @around(methods().decorated_with(query))
    def call_query(self, invocation: Invocation):
        func = invocation.func
        instance : BaseRepository = invocation.args[0]
        args = invocation.args
        kwargs = invocation.kwargs

        method_name = func.__name__
        result = instance._invoke_dynamic_query(method_name, *args[1:], **kwargs)
        return result