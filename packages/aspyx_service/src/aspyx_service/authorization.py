"""
authorization logic
"""
import inspect
from abc import abstractmethod, ABC
from typing import Optional, Callable

from aspyx.di import injectable, inject, order
from aspyx.di.aop import Invocation
from aspyx.reflection import TypeDescriptor, Decorators

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
    """
    The authorization manager is used to remember and execute pluggable authorization checks.
    """
    class Authorization():
        """
        Base class for authorization checks
        """
        def authorize(self, invocation: Invocation):
            """
            execute the authorization check. Throws an exception in case of violations
            """

    class AuthorizationFactory(ABC):
        """
        An authorization factory is used to create possible authorization checks given a method descriptor
        """

        def __init__(self, order = 0):
            self.order = order

        @abstractmethod
        def compute_authorization(self, method_descriptor: TypeDescriptor.MethodDescriptor) -> Optional['AuthorizationManager.Authorization']:
            """
            return a possible authorization check given a method descriptor
            Args:
                method_descriptor: the corresponding method descriptor

            Returns:
                an authorization check or None
            """

    # constructor

    def __init__(self):
        self.factories : list[AuthorizationManager.AuthorizationFactory] = []
        self.checks : dict[Callable, list[AuthorizationManager.Authorization]] = {}

    # public

    def register_factory(self, factory: 'AuthorizationManager.AuthorizationFactory'):
        self.factories.append(factory)

        self.factories.sort(key=lambda factory: factory.order)

    # internal

    def compute_checks(self, func: Callable) -> list[Authorization]:
        checks = []

        clazz = get_method_class(func)

        descriptor = TypeDescriptor.for_type(clazz).get_method(func.__name__)

        for factory in self.factories:
            check = factory.compute_authorization(descriptor)
            if check is not None:
                checks.append(check)

        return checks

    def get_checks(self, func: Callable) -> list[Authorization]:
        """
        return a list of authorization checks given a function.

        Args:
            func: the corresponding function.

        Returns:
            list of authorization checks
        """
        checks = self.checks.get(func, None)
        if checks is None:
            checks = self.compute_checks(func)
            self.checks[func] = checks
            print(checks)

        return checks

    def authorize(self, invocation: Invocation):
        for check in self.get_checks(invocation.func):
            check.authorize(invocation)

class AbstractAuthorizationFactory(AuthorizationManager.AuthorizationFactory):
    """
    Abstract base class for authorization factories
    """

    # constructor

    def __init__(self):
        super().__init__(0)

        if Decorators.has_decorator(type(self), order):
            self.order = Decorators.get_decorator(type(self), order).args[0]

    # inject

    @inject()
    def set_authorization_manager(self, authorization_manager: AuthorizationManager):
        authorization_manager.register_factory(self)
