"""
Tests
"""
import pytest

from .common import TestAsyncService, TestAsyncRestService, Pydantic, Data, service_manager, EmbeddedPydantic, \
    EmbeddedDataClass

embedded_pydantic=EmbeddedPydantic(int_attr=1, float_attr=1.0, bool_attr=True, str_attr="s")
embedded_dataclass=EmbeddedDataClass(int_attr=1, float_attr=1.0, bool_attr=True, str_attr="s")
pydantic = Pydantic(int_attr=1, float_attr=1.0, bool_attr=True, str_attr="s", int_list_attr=[1], float_list_attr=[1.0], bool_list_attr=[True], str_list_attr=[""],
                    embedded_pydantic=embedded_pydantic,
                    embedded_dataclass=embedded_dataclass,
                    embedded_pydantic_list =[embedded_pydantic],
                    embedded_dataclass_list=[embedded_dataclass])
data = Data(int_attr=1, float_attr=1.0, bool_attr=True, str_attr="s", int_list_attr=[1], float_list_attr=[1.0], bool_list_attr=[True], str_list_attr=[""])


class TestAsyncRemoteService:
    @pytest.mark.asyncio
    async def xtest(self, service_manager):

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
