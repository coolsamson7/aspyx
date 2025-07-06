import inspect
from abc import abstractmethod, ABC
from typing import Optional, Callable

from aspyx.di import injectable, inject
from aspyx.reflection import TypeDescriptor


class AuthorizationException(Exception):
    pass

def get_method_class(method):
    if inspect.ismethod(method) or inspect.isfunction(method):
        qualname = method.__qualname__
        parts = qualname.split('.')
        if len(parts) > 1:
            cls_name = parts[-2]
            module = inspect.getmodule(method)
            if module:
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if name == cls_name and hasattr(obj, method.__name__):
                        return obj
    return None

@injectable()
class AuthorizationManager:
    class Check():
        def check(self):
            pass

    class Analyzer(ABC):
        @abstractmethod
        def compute_check(self, method_descriptor: TypeDescriptor.MethodDescriptor) -> Optional['AuthorizationManager.Check']:
            pass

    # constructor

    def __init__(self):
        self.analyzers : list[AuthorizationManager.Analyzer] = []
        self.checks : dict[Callable, list[AuthorizationManager.Check]] = {}

    # public

    def register_analyzer(self, analyzer: 'AuthorizationManager.Analyzer'):
        self.analyzers.append(analyzer)

    # internal

    def compute_checks(self, func: Callable) -> list[Check]:
        checks = []

        clazz = get_method_class(func)

        descriptor = TypeDescriptor.for_type(clazz).get_method(func.__name__)

        for analyzer in self.analyzers:
            check = analyzer.compute_check(descriptor)
            if check is not None:
                checks.append(check)

        return checks


    # public

    def get_checks(self, func: Callable) -> list[Check]:
        checks = self.checks.get(func, None)
        if checks is None:
            checks = self.compute_checks(func)
            self.checks[func] = checks

        return checks

class AbstractAnalyzer(AuthorizationManager.Analyzer):
    def __init__(self):
        pass

    @inject()
    def set_authorization_manager(self, authorization_manager: AuthorizationManager):
        authorization_manager.register_analyzer(self)