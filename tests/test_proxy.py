from __future__ import annotations

import unittest

from aspyx.reflection import DynamicProxy


class Handler(DynamicProxy.InvocationHandler):
    def invoke(self, invocation: DynamicProxy.Invocation):
        return invocation.args[0]

class Service:
    def say(self, message: str) -> str:
        pass

class TestProxy(unittest.TestCase):
    def test_proxy(self):
        proxy = DynamicProxy.create(Service, Handler())

        answer = proxy.say("hello")
        self.assertEqual(answer, "hello")


if __name__ == '__main__':
    unittest.main()