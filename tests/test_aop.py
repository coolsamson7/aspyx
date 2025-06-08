from __future__ import annotations

import logging
import unittest

from aspyx.aop.aop import AOPConfiguration, classes
from aspyx.reflection import Decorators
from aspyx.di import injectable, inject, Environment, configuration
from aspyx.aop import advice, before, after, around, methods, Invocation


def transactional():
    def decorator(func):
        Decorators.add(func, transactional)
        return func

    return decorator

@configuration(imports=[AOPConfiguration])
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
    # constructor

    def __init__(self):
        self.name = "SampleAdvice"

        self.before_calls = 0
        self.after_calls = 0
        self.around_calls = 0
        self.error_calls = 0

    # public

    def reset(self):
        self.before_calls = 0
        self.after_calls = 0
        self.around_calls = 0
        self.error_calls = 0

    # aspects

    @before(methods().named("say").ofType(Foo).matches(".*"))
    def callBeforeFoo(self, invocation: Invocation):
        self.before_calls += 1

    @before(methods().named("say").ofType(Bar))
    def callBeforeBar(self, invocation: Invocation):
        self.before_calls += 1

    @after(methods().named("say"))
    def callAfter(self, invocation: Invocation):
        self.after_calls += 1

    @around(methods().named("say"))
    def callAround(self, invocation: Invocation):
        self.around_calls += 1

        return invocation.proceed()

    @around(methods().decoratedWith(transactional))
    def callTransactional1(self, invocation: Invocation):
        self.around_calls += 1

        return invocation.proceed()
    
    #@around(classes().decoratedWith(transactional))
    def callTransactional(self, invocation: Invocation):
        self.around_calls += 1

        return invocation.proceed()

class TestInjector(unittest.TestCase):
    def test_injector(self):
        logging.basicConfig(level=logging.DEBUG)

        environment = Environment(Configuration)  # creates eagerly!

        advice = environment.get(SampleAdvice)

        foo = environment.get(Foo)

        self.assertIsNotNone(foo)

        # foo

        result = foo.say("hello")

        self.assertEqual(result, "hello")

        self.assertEqual(advice.before_calls, 1)
        self.assertEqual(advice.around_calls, 1)
        self.assertEqual(advice.after_calls, 1)

        advice.reset()

        # bar

        result = foo.bar.say("hello")

        self.assertEqual(result, "hello")

        self.assertEqual(advice.before_calls, 1)
        self.assertEqual(advice.around_calls, 2)
        self.assertEqual(advice.after_calls, 1)


if __name__ == '__main__':
    unittest.main()