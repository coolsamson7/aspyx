from __future__ import annotations

import unittest

from aspyx.di import component, on_init, on_destroy, environmentAware, inject, Factory, create, configuration, Environment, PostProcessor, factory



@component()
class SamplePostProcessor(PostProcessor):
    def process(self, instance: object):
        print(f"created a {instance}")

class Foo:
    pass

#@component()
class Baz:
    pass

@component()
class Bar:
    def __init__(self, foo: Foo):
        self.foo = foo

    @on_init()
    def init(self):
        print("init bar")

    @on_destroy()
    def destroy(self):
        print("destroy bar")

    @environmentAware()
    def initEnvironment(self, env: Environment):
        print("set environment bar")

    @inject()
    def set_baz(self, baz: Baz) -> None:
        print("set bar.baz")
        pass

@factory()
class TestFactory(Factory[Foo]):
    def __init__(self): # TODO will it break without it?
        pass

    def create(self) -> Foo:
        return Foo()

@configuration()
@component()
class Configuration:
    # constructor

    def __init__(self): # TODO will it break without it?
        pass

    # create some beans

    @create()
    def create(self) -> Baz:
        return Baz()

class TestInject(unittest.TestCase):
    def test_1(self):
        env = Environment()

        bar = env.get(Bar)
        foo = env.get(Foo)

        env.shutdown()


if __name__ == '__main__':
   unittest.main()