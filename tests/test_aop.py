"""
Tests for the AOP (Aspect-Oriented Programming) functionality in the aspyx.di module.
"""
from __future__ import annotations

import asyncio
import logging
import unittest
from typing import Dict

from aspyx.di.threading import synchronized
from aspyx.reflection import Decorators
from aspyx.di import injectable, Environment, environment
from aspyx.di.aop import advice, before, after, around, methods, Invocation, error, classes

logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)s in %(filename)s:%(lineno)d - %(message)s'
)

def configure_logging(levels: Dict[str, int]) -> None:
    for name in levels:
        logging.getLogger(name).setLevel(levels[name])

configure_logging({"aspyx": logging.DEBUG})

def transactional():
    def decorator(func):
        Decorators.add(func, transactional)
        return func #

    return decorator

@environment()
class SampleEnvironment:
    def __init__(self):
        pass


@injectable()
@transactional()
class Bar:
    def __init__(self):
        pass

    async def say_async(self, message: str):
        await asyncio.sleep(0.01)

        return f"hello {message}"

    @synchronized()
    def say(self, message: str):
        return f"hello {message}"

@injectable()
class Foo:
    def __init__(self, bar: Bar):
        self.bar = bar

    @synchronized()
    def say(self, message: str):
        return f"hello {message}"

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
    def call_before_foo(self, invocation: Invocation):
        self.before_calls += 1

    @before(methods().named("say").of_type(Bar))
    def call_before_bar(self, invocation: Invocation):
        self.before_calls += 1

    @after(methods().named("say"))
    def call_after(self, invocation: Invocation):
        self.after_calls += 1

    @around(methods().that_are_async())
    async def call_around_async(self, invocation: Invocation):
        self.around_calls += 1

        print("call_around_async")

        return await invocation.proceed_async()

    @around(methods().named("say"))
    def call_around(self, invocation: Invocation):
        self.around_calls += 1

        args = [invocation.args[0],invocation.args[1] + "!"]

        return invocation.proceed(*args)

    @around(methods().decorated_with(transactional), classes().decorated_with(transactional))
    def call_transactional1(self, invocation: Invocation):
        self.around_calls += 1

        return invocation.proceed()

    #@around(classes().decoratedWith(transactional))
    def call_transactional(self, invocation: Invocation):
        self.around_calls += 1

        return invocation.proceed()

environment = Environment(SampleEnvironment)

class TestAsyncAdvice(unittest.IsolatedAsyncioTestCase):
    async def xtest_async(self):
        bar = environment.get(Bar)

        result = await bar.say_async("world")

        self.assertEqual(result, "hello world")

class TestAdvice(unittest.TestCase):

    def test_advice(self):
        advice = environment.get(SampleAdvice)

        foo = environment.get(Foo)

        self.assertIsNotNone(foo)

        # foo

        result = foo.say("world")

        self.assertEqual(result, "hello world!")

        self.assertEqual(advice.before_calls, 1)
        self.assertEqual(advice.around_calls, 1)
        self.assertEqual(advice.after_calls, 1)

        advice.reset()

        # bar

        result = foo.bar.say("world")

        self.assertEqual(result, "hello world!")

        self.assertEqual(advice.before_calls, 1)
        self.assertEqual(advice.around_calls, 2)
        self.assertEqual(advice.after_calls, 1)

    def test_error(self):
        foo = environment.get(Foo)
        advice = environment.get(SampleAdvice)

        try:
            foo.throw_error()
        except Exception as e:#
            self.assertIs(e, advice.exception)

        # foo

        foo.say("hello")

if __name__ == '__main__':
    unittest.main()
