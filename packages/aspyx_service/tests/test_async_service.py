"""
Tests
"""
import unittest

import pytest

from packages.aspyx_service.tests.common import TestAsyncService, start_server, TestService, TestAsyncRestService, \
    Pydantic, Data, Test


pydantic = Pydantic(i=1, f=1.0, b=True, s="s")
data = Data(i=1, f=1.0, b=True, s="s", p=pydantic)

class TestLocalService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service_manager = start_server()

    def test_local(self):
        test_service = self.service_manager.get_service(TestService, preferred_channel="local")

        result = test_service.hello("hello")
        self.assertEqual(result, "hello")

        result_data = test_service.data(data)
        self.assertEqual(result_data, data)

        result_pydantic = test_service.pydantic(pydantic)
        self.assertEqual(result_pydantic, pydantic)

    def test_inject(self):
        test = self.service_manager.environment.get(Test)

        self.assertIsNotNone(test.service)

class TestAsyncRemoteService(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.service_manager = start_server()

    async def test_dispatch_json(self):
        test_service = self.service_manager.get_service(TestAsyncService, preferred_channel="dispatch-json")

        result = await test_service.hello("hello")
        self.assertEqual(result, "hello")

        result_data = await test_service.data(data)
        self.assertEqual(result_data, data)

        result_pydantic = await test_service.pydantic(pydantic)
        self.assertEqual(result_pydantic, pydantic)

    async def test_dispatch_msgpack(self):
        test_service = self.service_manager.get_service(TestAsyncService, preferred_channel="dispatch-msgpack")

        result = await test_service.hello("hello")
        self.assertEqual(result, "hello")

        result_data = await test_service.data(data)
        self.assertEqual(result_data, data)

        result_pydantic = await test_service.pydantic(pydantic)
        self.assertEqual(result_pydantic, pydantic)

    async def xtest_dispatch_rest(self):
        test_service = self.service_manager.get_service(TestAsyncRestService, preferred_channel="rest")

        result = await test_service.get("hello")
        self.assertEqual(result, "hello")

        result = await test_service.put("hello")
        self.assertEqual(result, "hello")

        result = await test_service.delete("hello")
        self.assertEqual(result, "hello")

        #

        # result_pydantic = test_service.post_pydantic(pydantic)
        # self.assertEqual(result_pydantic, pydantic)

        ##result_pydantic = test_service.post_data(pydantic)
        # self.assertEqual(result_pydantic, pydantic)