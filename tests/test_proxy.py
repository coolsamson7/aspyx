"""
Test for DynamicProxy in aspyx.reflection
"""
from __future__ import annotations

import unittest

from aspyx.reflection import DynamicProxy


class Handler(DynamicProxy.InvocationHandler):
    def invoke(self, invocation: DynamicProxy.Invocation):
        return invocation.args[0]

    async def invoke_async(self, invocation: 'DynamicProxy.Invocation'):
        return invocation.args[0]

class Service:
    def say(self, message: str) -> str:
        pass

    async def say_async(self, message: str) -> str:
        return message

class TestAsyncProxyAsync(unittest.IsolatedAsyncioTestCase):
    async def test_async_proxy(self):
        proxy = DynamicProxy.create(Service, Handler())

        answer = await proxy.say_async("hello")
        self.assertEqual(answer, "hello")

class TestProxy(unittest.TestCase):
    def test_proxy(self):
        proxy = DynamicProxy.create(Service, Handler())

        answer = proxy.say("hello")
        self.assertEqual(answer, "hello")


if __name__ == '__main__':
    unittest.main()
