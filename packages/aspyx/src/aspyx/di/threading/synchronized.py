"""
Synchronized decorator and advice
"""
from __future__ import annotations

import threading
from weakref import WeakKeyDictionary

from aspyx.reflection import Decorators
from aspyx.di.aop import advice, around, methods, Invocation

def synchronized():
    """
    decorate methods to synchronize them based on an instance related `RLock`
    """
    def decorator(func):
        Decorators.add(func, synchronized)
        return func #

    return decorator

@advice
class SynchronizeAdvice:
    # constructor

    def __init__(self):
        self.locks = WeakKeyDictionary()

    # internal

    def get_lock(self, instance) -> threading.RLock:
        lock = self.locks.get(instance, None)
        if lock is None:
            lock = threading.RLock()
            self.locks[instance] = lock

        return lock

    # around

    @around(methods().decorated_with(synchronized))
    def synchronize_sync(self, invocation: Invocation):
        with self.get_lock(invocation.args[0]):
            return invocation.proceed()

    @around(methods().decorated_with(synchronized).that_are_async())
    async def synchronize_async(self, invocation: Invocation):
        with self.get_lock(invocation.args[0]):
            return await invocation.proceed_async()
