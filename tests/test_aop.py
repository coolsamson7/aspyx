from __future__ import annotations

import logging
import unittest

from aspyx.reflection import Decorators
from aspyx.di import component, inject, Environment
from aspyx.aop import advice, before, after, around, methods, Invocation


def transactional():
    def decorator(func):
        Decorators.add(func, transactional)
        return func

    return decorator


@component()
class Bar:
    def __init__(self, foo: 'Foo'):
        print("new bar")

    @transactional()
    def say(self, hello: str):
        print("BAR: " + hello)
        return hello

@component()
class Foo:
    def __init__(self, bar: Bar):
        print("new foo")
        self.bar = bar

    @inject()
    def set_bar(self, bar: Bar):
        pass

    def say(self, hello: str):
        print("foo: " + hello)
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

# test

# main

class TestInjector(unittest.TestCase):
    def test_injector(self):
        logging.basicConfig(level=logging.DEBUG)

        environment = Environment()  # creates eagerly!

        foo = environment.get(Foo)

        self.assertIsNotNone(foo)

        foo1 = environment.get(Foo)  # should be a noop

        self.assertTrue(foo is foo1, "should be identical")

        result = foo.say("hello")
        self.assertEqual(result, "hello")

        result = foo.bar.say("hello")
        self.assertEqual(result, "hello")


if __name__ == '__main__':
    unittest.main()