"""
Dynamic proxies for method interception and delegation.
"""
from typing import Generic, TypeVar, Type

T = TypeVar("T")

class DynamicProxy(Generic[T]):
    """
    DynamicProxy enables dynamic method interception and delegation for any class type.

    It is used to create proxy objects that forward method calls to a custom InvocationHandler.
    This allows for advanced patterns such as aspect-oriented programming, logging, or remote invocation,
    by intercepting method calls at runtime and handling them as needed.

    Usage:
        class MyHandler(DynamicProxy.InvocationHandler):
            def invoke(self, invocation):
                print(f"Intercepted: {invocation.name}")
                # custom logic here
                return ...

        proxy = DynamicProxy.create(SomeClass, MyHandler())
        proxy.some_method(args)  # Will be intercepted by MyHandler.invoke

    Attributes:
        type: The proxied class type.
        invocation_handler: The handler that processes intercepted method calls.
    """
    # inner class

    class Invocation:
        def __init__(self, type: Type[T], name: str, *args, **kwargs):
            self.type = type
            self.name = name
            self.args = args
            self.kwargs = kwargs

    class InvocationHandler:
        def invoke(self, invocation: 'DynamicProxy.Invocation'):
            pass

    # class methods

    @classmethod
    def create(cls, type: Type[T], invocation_handler: 'DynamicProxy.InvocationHandler') -> T:
        return DynamicProxy(type, invocation_handler)

    # constructor

    def __init__(self, type: Type[T], invocation_handler: 'DynamicProxy.InvocationHandler'):
        self.type = type
        self.invocation_handler = invocation_handler

    # public

    def __getattr__(self, name):
        def wrapper(*args, **kwargs):
            return self.invocation_handler.invoke(DynamicProxy.Invocation(self.type, name, *args, **kwargs))

        return wrapper
