from __future__ import annotations

import logging
import unittest

from aspyx.reflection import Decorators
from aspyx.di import injectable, Environment, environment
from aspyx.di.aop import advice, before, after, around, methods, Invocation, error, classes


def transactional():
    def decorator(func):
        Decorators.add(func, transactional)
        return func #

    return decorator

@environment()
class TestEnvironment:
    def __init__(self):
        pass


@injectable()
@transactional()
class Bar:
    def __init__(self):
        pass

    #@transactional()
    def say(self, hello: str):
        return hello

@injectable()
class Foo:
    def __init__(self, bar: Bar):
        self.bar = bar

    def say(self, hello: str):
        return hello

    def throw_error(self):
        raise Exception("ouch")

@advice
class SampleAdvice:
    # constructor

    def __init__(self):
        self.name = "SampleAdvice"

        self.before_calls = 0
        self.after_calls = 0
        self.around_calls = 0
        self.error_calls = 0

        self.exception = None

    # public

    def reset(self):
        self.before_calls = 0
        self.after_calls = 0
        self.around_calls = 0
        self.error_calls = 0

        self.exception = None

    # aspects

    @error(methods().of_type(Foo).matches(".*"))
    def error(self, invocation: Invocation):
        self.exception = invocation.exception

    @before(methods().named("say").of_type(Foo).matches(".*"))
    def callBeforeFoo(self, invocation: Invocation):
        self.before_calls += 1

    @before(methods().named("say").of_type(Bar))
    def callBeforeBar(self, invocation: Invocation):
        self.before_calls += 1

    @after(methods().named("say"))
    def callAfter(self, invocation: Invocation):
        self.after_calls += 1

    @around(methods().named("say"))
    def callAround(self, invocation: Invocation):
        self.around_calls += 1

        return invocation.proceed()

    @around(methods().decorated_with(transactional), classes().decorated_with(transactional))
    def callTransactional1(self, invocation: Invocation):
        self.around_calls += 1

        return invocation.proceed()
    
    #@around(classes().decoratedWith(transactional))
    def callTransactional(self, invocation: Invocation):
        self.around_calls += 1

        return invocation.proceed()

#logging.basicConfig(level=logging.DEBUG)

class TestAdvice(unittest.TestCase):
    testEnvironment = Environment(TestEnvironment)

    def test_advice(self):
        environment = TestAdvice.testEnvironment

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

    def test_error(self):
        environment = TestAdvice.testEnvironment


        foo = environment.get(Foo)
        advice = environment.get(SampleAdvice)

        try:
            foo.throw_error()
        except Exception as e:#
            self.assertIs(e, advice.exception)

        # foo

        result = foo.say("hello")

if __name__ == '__main__':
    unittest.main()