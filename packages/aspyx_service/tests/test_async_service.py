"""
Tests
"""
import pytest

from .common import TestAsyncService, TestAsyncRestService, Pydantic, Data, service_manager

pydantic = Pydantic(i=1, f=1.0, b=True, s="s")
data = Data(i=1, f=1.0, b=True, s="s")

@pytest.mark.asyncio(scope="function")
class TestAsyncRemoteService():
    async def test(self, service_manager):

        # dispatch json

        test_service = service_manager.get_service(TestAsyncService, preferred_channel="dispatch-json")

        result = await test_service.hello("hello")
        assert result == "hello"

        result_data = await test_service.data(data)
        assert result_data == data

        result_pydantic = await test_service.pydantic(pydantic)
        assert result_pydantic == pydantic

        # msgpack

        test_service = service_manager.get_service(TestAsyncService, preferred_channel="dispatch-msgpack")

        result = await test_service.hello("hello")
        assert result == "hello"

        result_data = await test_service.data(data)
        assert result_data == data

        result_pydantic = await test_service.pydantic(pydantic)
        assert result_pydantic == pydantic

        # rest

        test_service = service_manager.get_service(TestAsyncRestService, preferred_channel="rest")

        result = await test_service.get("hello")
        assert result == "hello"

        result = await test_service.put("hello")
        assert result =="hello"

        result = await test_service.delete("hello")
        assert result == "hello"

        result_pydantic = await test_service.post_pydantic("message", pydantic)
        assert result_pydantic == pydantic

        result_data = await test_service.post_data("message", data)
        assert result_data == data
