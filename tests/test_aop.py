from __future__ import annotations

import logging
import unittest

from aspyx.reflection import Decorators
from aspyx.di import injectable, inject, Environment, configuration
from aspyx.aop import advice, before, after, around, methods, Invocation


def transactional():
    def decorator(func):
        Decorators.add(func, transactional)
        return func

    return decorator

@configuration()
class Configuration:
    def __init__(self):
        pass


@injectable()
class Bar:
    def __init__(self):
        pass

    @transactional()
    def say(self, hello: str):
        return hello

@injectable()
class Foo:
    def __init__(self, bar: Bar):
        self.bar = bar

    def say(self, hello: str):
        return hello

@advice
class SampleAdvice:
    def __init__(self):
        self.name = "SampleAdvice"
        pass

    @before(methods().named("say").ofType(Foo))
    def callBeforeFoo(self, invocation: Invocation):
        print("Before foo method execution")

    @before(methods().named("say").ofType(Bar))
    def callBeforeBar(self, invocation: Invocation):
        print("Before bar method execution")

    @after(methods().named("say"))
    def callAfter(self, invocation: Invocation):
        print("after method execution")

    @around(methods().named("say"))
    def callAround(self, invocation: Invocation):
        print("around method execution")

        return invocation.proceed()

    @around(methods().decoratedWith(transactional))
    def callTransactional(self, invocation: Invocation):
        print("around transactional methods")

        return invocation.proceed()

class TestInjector(unittest.TestCase):
    def test_injector(self):
        logging.basicConfig(level=logging.DEBUG)

        environment = Environment(Configuration)  # creates eagerly!

        foo = environment.get(Foo)

        self.assertIsNotNone(foo)

        result = foo.say("hello")
        self.assertEqual(result, "hello")

        result = foo.bar.say("hello")
        self.assertEqual(result, "hello")


if __name__ == '__main__':
    unittest.main()