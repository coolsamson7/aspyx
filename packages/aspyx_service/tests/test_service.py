"""
Tests
"""

import unittest

from .common import TestService, TestRestService, Test, Pydantic, Data, service_manager

pydantic = Pydantic(i=1, f=1.0, b=True, s="s")
data = Data(i=1, f=1.0, b=True, s="s", p=pydantic)


class TestLocalService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service_manager = service_manager()

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

class TestSyncRemoteService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service_manager = service_manager()

    def xtest_dispatch_json(self):
        test_service = self.service_manager.get_service(TestService, preferred_channel="dispatch-json")

        result = test_service.hello("hello")
        self.assertEqual(result, "hello")

        result_data = test_service.data(data)
        self.assertEqual(result_data, data)

        result_pydantic = test_service.pydantic(pydantic)
        self.assertEqual(result_pydantic, pydantic)

    def xtest_dispatch_msgpack(self):
        test_service = self.service_manager.get_service(TestService, preferred_channel="dispatch-msgpack")

        result = test_service.hello("hello")
        self.assertEqual(result, "hello")

        result_data = test_service.data(data)
        self.assertEqual(result_data, data)

        result_pydantic = test_service.pydantic(pydantic)
        self.assertEqual(result_pydantic, pydantic)

    def test_dispatch_rest(self):
        test_service = self.service_manager.get_service(TestRestService, preferred_channel="rest")

        result = test_service.get("hello")
        self.assertEqual(result, "hello")

        result = test_service.put("hello")
        self.assertEqual(result, "hello")

        result = test_service.delete("hello")
        self.assertEqual(result, "hello")

        # data and pydantic

        result_pydantic = test_service.post_pydantic("message", pydantic)
        self.assertEqual(result_pydantic, pydantic)

        #result_data= test_service.post_data("message", data)
        #self.assertEqual(result_data, data)
