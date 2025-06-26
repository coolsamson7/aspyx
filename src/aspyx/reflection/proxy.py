"""
Dynamic proxies for method interception and delegation.
"""
import inspect
from typing import Generic, TypeVar, Type, Callable

T = TypeVar("T")

class DynamicProxy(Generic[T]):
    """
    DynamicProxy enables dynamic method interception and delegation for any class type.

    It is used to create proxy objects that forward method calls to a custom InvocationHandler.
    This allows for advanced patterns such as aspect-oriented programming, logging, or remote invocation,
    by intercepting method calls at runtime and handling them as needed.

    Usage:
    ```python
        class MyHandler(DynamicProxy.InvocationHandler):
            def invoke(self, invocation):
                print(f"Intercepted: {invocation.name}")
                # custom logic here
                return ...

        proxy = DynamicProxy.create(SomeClass, MyHandler())
        proxy.some_method(args)  # Will be intercepted by MyHandler.invoke
    ```
    """
    # inner class

    class Invocation:
        __slots__ = [
            "type",
            "method",
            "args",
            "kwargs",
        ]

        # constructor

        def __init__(self, type: Type[T], method: Callable, *args, **kwargs):
            self.type = type
            self.method = method
            self.args = args
            self.kwargs = kwargs

    class InvocationHandler:
        def invoke(self, invocation: 'DynamicProxy.Invocation'):
            pass

        async def invoke_async(self, invocation: 'DynamicProxy.Invocation'):
            return self.invoke(invocation)

    # class methods

    @classmethod
    def create(cls, type: Type[T], invocation_handler: 'DynamicProxy.InvocationHandler') -> T:
        return DynamicProxy(type, invocation_handler)

    __slots__ = [
        "type",
        "invocation_handler"
    ]

    # constructor

    def __init__(self, type: Type[T], invocation_handler: 'DynamicProxy.InvocationHandler'):
        self.type = type
        self.invocation_handler = invocation_handler

    # public

    def __getattr__(self, name):
        method = getattr(self.type, name)

        if  inspect.iscoroutinefunction(method):
            async def async_wrapper(*args, **kwargs):
                return  await self.invocation_handler.invoke_async(DynamicProxy.Invocation(self.type, method, *args, **kwargs))

            return async_wrapper

        else:
            def sync_wrapper(*args, **kwargs):
                return self.invocation_handler.invoke(DynamicProxy.Invocation(self.type, method, *args, **kwargs))

            return sync_wrapper
