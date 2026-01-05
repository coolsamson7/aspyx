"""
Tests
"""
import logging

from aspyx_service.generator import OpenAPIGenerator, JSONSchemaGenerator

from aspyx.util import Logger

Logger.configure(default_level=logging.INFO, levels={
    "httpx": logging.ERROR,
    "aspyx.di": logging.INFO,
    "aspyx.di.aop": logging.ERROR,
    "aspyx.service": logging.DEBUG,
    "aspyx.event": logging.INFO
})


from .common import TestService, TestRestService, Pydantic, Data, service_manager, EmbeddedPydantic, \
    EmbeddedDataClass

embedded_pydantic=EmbeddedPydantic(int_attr=1, float_attr=1.0, bool_attr=True, str_attr="s")
embedded_dataclass=EmbeddedDataClass(int_attr=1, float_attr=1.0, bool_attr=True, str_attr="s")
pydantic = Pydantic(int_attr=1, float_attr=1.0, bool_attr=True, str_attr="s", int_list_attr=[1], float_list_attr=[1.0], bool_list_attr=[True], str_list_attr=[""],
                    embedded_pydantic=embedded_pydantic,
                    embedded_dataclass=embedded_dataclass,
                    embedded_pydantic_list =[embedded_pydantic],
                    embedded_dataclass_list=[embedded_dataclass])
data = Data(int_attr=1, float_attr=1.0, bool_attr=True, str_attr="s", int_list_attr=[1], float_list_attr=[1.0], bool_list_attr=[True], str_list_attr=[""])

class TestLocalService:
    def test_openapi(self, service_manager):
        open_api = OpenAPIGenerator(service_manager).generate()

        json_str = OpenAPIGenerator(service_manager).to_json()  # pretty-printed JSON
        print(json_str)
        json_str = JSONSchemaGenerator(service_manager).to_json()  # pretty-printed JSON
        print(json_str)


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

class TestSyncRemoteService:
    def test_dispatch_json(self, service_manager):
        test_service = service_manager.get_service(TestService, preferred_channel="dispatch-json")

        result = test_service.hello("hello")
        assert result == "hello"

        result_data = test_service.data(data)
        assert result_data == data

        result_pydantic = test_service.pydantic(pydantic)
        assert result_pydantic == pydantic

    def test_dispatch_protobuf(self, service_manager):
        test_service = service_manager.get_service(TestService, preferred_channel="dispatch-protobuf")

        result = test_service.hello("hello")
        assert result == "hello"

        result_data = test_service.data(data)
        assert result_data == data

        result_pydantic = test_service.pydantic(pydantic)
        assert result_pydantic == pydantic


    def test_dispatch_msgpack(self, service_manager):
        test_service = service_manager.get_service(TestService, preferred_channel="dispatch-msgpack")

        result = test_service.hello("hello")
        assert result == "hello"

        result_data = test_service.data(data)
        assert result_data == data

        result_pydantic = test_service.pydantic(pydantic)
        assert result_pydantic == pydantic

    def test_dispatch_rest(self, service_manager):
        test_service = service_manager.get_service(TestRestService, preferred_channel="rest")

        result = test_service.test_get("p", "qp")
        assert result == "pqp"

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
