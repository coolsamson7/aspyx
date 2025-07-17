"""
Tests
"""

from .common import TestService, TestRestService, Pydantic, Data, service_manager, Foo

pydantic = Pydantic(i=1, f=1.0, b=True, s="s")
data = Data(i=1, f=1.0, b=True, s="s")


class TestLocalService():
    def test_local(self, service_manager):
        test_service = service_manager.get_service(TestService, preferred_channel="local")

        result = test_service.hello("hello")
        assert result == "hello"

        result_data = test_service.data(data)
        assert result_data == data

        result_pydantic = test_service.pydantic(pydantic)
        assert result_pydantic == pydantic

    def test_throw(self, service_manager):
        test_service = service_manager.get_service(TestService, preferred_channel="local")

        try:
            test_service.throw("hello")
        except Exception as e:
            print(e)

    def test_inject(self, service_manager):
        test = service_manager.environment.get(Foo)

        assert test.service is not None

class TestSyncRemoteService:
    def test_dispatch_json(self, service_manager):
        test_service = service_manager.get_service(TestService, preferred_channel="dispatch-json")

        result = test_service.hello("hello")
        assert result == "hello"

        result_data = test_service.data(data)
        assert result_data == data

        result_pydantic = test_service.pydantic(pydantic)
        assert result_pydantic == pydantic

    def xtest_dispatch_msgpack(self, service_manager):
        test_service = service_manager.get_service(TestService, preferred_channel="dispatch-msgpack")

        result = test_service.hello("hello")
        assert result == "hello"

        result_data = test_service.data(data)
        assert result_data == data

        result_pydantic = test_service.pydantic(pydantic)
        assert result_pydantic == pydantic

    def xtest_dispatch_rest(self, service_manager):
        test_service = service_manager.get_service(TestRestService, preferred_channel="rest")

        result = test_service.get("hello")
        assert result == "hello"

        result = test_service.put("hello")
        assert result == "hello"

        result = test_service.delete("hello")
        assert result == "hello"

        # data and pydantic

        result_pydantic = test_service.post_pydantic("message", pydantic)
        assert result_pydantic == pydantic

        result_data= test_service.post_data("message", data)
        assert result_data == data
