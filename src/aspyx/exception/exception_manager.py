"""
Exception handling code
"""
from threading import RLock
from typing import Any, Callable, Dict, Optional, Type

from aspyx.di import injectable, Environment, inject_environment, on_running
from aspyx.reflection import Decorators, TypeDescriptor
from aspyx.threading import ThreadLocal


def exception_handler():
    """
    This annotation is used to mark classes that container handlers for exceptions
    """
    def decorator(cls):
        Decorators.add(cls, exception_handler)

        ExceptionManager.exception_handler_classes.append(cls)

        return cls

    return decorator

def handle():
    """
    Any method annotated with @handle will be registered as an exception handler method.
    """
    def decorator(func):
        Decorators.add(func, handle)
        return func

    return decorator

class ErrorContext():
    pass

class Handler:
    # constructor

    def __init__(self, type_: Type, instance: Any, handler: Callable):
        self.type = type_
        self.instance = instance
        self.handler = handler

    def handle(self, exception: BaseException):
        self.handler(self.instance, exception)

class Chain:
    # constructor

    def __init__(self, handler: Handler, next: Optional[Handler] = None):
        self.handler = handler
        self.next = next

    # public

    def handle(self, exception: BaseException):
        self.handler.handle(exception)

class Invocation:
    def __init__(self, exception: Exception, chain: Chain):
        self.exception = exception
        self.chain = chain
        self.current = self.chain

@injectable()
class ExceptionManager:
    """
    An exception manager collects all registered handlers and is able to handle an exception
    by dispatching it to the most applicable handler ( according to mro )
    """
    # static data

    exception_handler_classes = []

    invocation = ThreadLocal()

    # class methods

    @classmethod
    def proceed(cls):
        invocation = cls.invocation.get()

        invocation.current = invocation.current.next
        if invocation.current is not None:
            invocation.current.handle(invocation.exception)

    # constructor

    def __init__(self):
        self.environment : Optional[Environment] = None
        self.handler : list[Handler] = []
        self.cache: Dict[Type, Chain] = {}
        self.lock = RLock()
        self.current_context: Optional[ErrorContext] = None

    # internal

    @inject_environment()
    def set_environment(self, environment: Environment):
        self.environment = environment

    @on_running()
    def setup(self):
        for handler_class in self.exception_handler_classes:
            type_descriptor = TypeDescriptor.for_type(handler_class)
            instance = self.environment.get(handler_class)

            # analyze methods

            for method in type_descriptor.get_methods():
                if method.has_decorator(handle):
                    if len(method.param_types) == 1:
                        exception_type = method.param_types[0]

                        self.handler.append(Handler(
                            exception_type,
                            instance,
                            method.method,
                        ))
                    else:
                        print(f"handler {method.method} expected to have one parameter")

    def get_handlers(self, clazz: Type) -> Optional[Chain]:
        chain = self.cache.get(clazz, None)
        if chain is None:
            with self.lock:
                chain = self.cache.get(clazz, None)
                if chain is None:
                    chain = self.compute_handlers(clazz)
                    self.cache[clazz] = chain

        return chain

    def compute_handlers(self, clazz: Type) -> Optional[Chain]:
        mro = clazz.mro()

        chain = []

        for type in mro:
            handler = next((handler for handler in self.handler if handler.type is type), None)
            if handler:
                chain.append(Chain(handler))

        # chain

        for i in range(0, len(chain) - 2):
            chain[i].next = chain[i + 1]

        if len(chain) > 0:
            return chain[0]
        else:
            return None

    def handle(self, exception: Exception):
        """
        handle an exception by invoking the most applicable handler ( according to mro )
        :param exception: the exception
        """
        chain = self.get_handlers(type(exception))
        if chain is not None:

            self.invocation.set(Invocation(exception, chain))
            try:
                chain.handle(exception)
            finally:
                self.invocation.clear()
