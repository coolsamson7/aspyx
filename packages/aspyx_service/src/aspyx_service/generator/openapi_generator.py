from typing import TypeVar

from pydantic import BaseModel
from fastapi.openapi.models import OpenAPI, Info, PathItem, Operation, Response, Parameter, RequestBody, \
    MediaType

from aspyx.reflection import TypeDescriptor
from aspyx_service import rest
from aspyx_service.restchannel import RestChannel

T = TypeVar("T")

class OpenAPIGenerator:
    PRIMITIVES = {
        str: {"type": "string"},
        int: {"type": "integer", "format": "int32"},
        float: {"type": "number", "format": "float"},
        bool: {"type": "boolean"},
    }

    def __init__(self, service_manager):
        self.service_manager = service_manager
        self.rest_channel: RestChannel = service_manager.environment.get(RestChannel)
        self.schemas: dict[type, dict] = {}

    def _get_schema_for_type(self, typ: type) -> dict:
        if typ in self.schemas:
            return self.schemas[typ]

        if typ in self.PRIMITIVES:
            schema = self.PRIMITIVES[typ]
        elif isinstance(typ, type) and issubclass(typ, BaseModel):
            schema = typ.model_json_schema()
        else:
            schema = {"type": "object"}

        self.schemas[typ] = schema
        return schema

    def generate(self) -> OpenAPI:
        from fastapi.openapi.models import Components

        openapi = OpenAPI(
            openapi="3.1.0",
            info=Info(title="My API", version="1.0.0"),
            paths={},
            components=Components(schemas={}),
        )

        for service_name, service in self.service_manager.descriptors_by_name.items():
            if service.is_component():
                continue

            descriptor = TypeDescriptor.for_type(service.type)

            if not descriptor.has_decorator(rest):
                continue

            print(service.type)

            for method_desc in descriptor.get_methods():
                call = self.rest_channel.get_call(service.type, method_desc.method)

                #if call.type != "get":
                #    continue

                path_item: PathItem = openapi.paths.get(call.url_template, PathItem())
                operation = Operation(
                    responses={"200": Response(description="Success")},
                    parameters=[],
                )

                # Add path parameters
                for name in call.path_param_names:
                    # get type hint
                    hint = next((p.type for p in method_desc.params if p.name == name), str)
                    operation.parameters.append(
                        Parameter(
                            name=name,
                            **{"in": "path"},  # Use dict unpacking to avoid keyword conflict
                            required=True,
                            schema=self._get_schema_for_type(hint),
                        )
                    )

                # Add query parameters
                for name in call.query_param_names:
                    hint = next((p.type for p in method_desc.params if p.name == name), str)
                    operation.parameters.append(
                        Parameter(
                            name=name,
                            **{"in": "query"},  # Use dict unpacking to avoid keyword conflict
                            required=True,
                            schema=self._get_schema_for_type(hint),
                        )
                    )

                # Add request body
                if call.body_param_name:
                    hint = next((p.type for p in method_desc.params if p.name == call.body_param_name), dict)
                    operation.request_body = RequestBody(
                        required=True,
                        content={"application/json": MediaType(schema=self._get_schema_for_type(hint))}
                    )

                # attach operation to HTTP method
                setattr(path_item, call.type.lower(), operation)
                openapi.paths[call.url_template] = path_item

        # attach all cached schemas
        openapi.components.schemas = {k.__name__: v for k, v in self.schemas.items()}

        return openapi

    def to_json(self, indent: int = 2) -> str:
        return self.generate().model_dump_json(
            indent=indent,
            exclude_none=True,
            by_alias=True
        )