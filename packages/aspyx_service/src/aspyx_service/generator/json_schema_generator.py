from typing import get_type_hints, get_origin, get_args, Any
import json

from pydantic import BaseModel

from aspyx.reflection import TypeDescriptor


class JSONSchemaGenerator:
    """
    Generates a JSON Schema-based service descriptor for framework-agnostic
    service discovery and handshaking between systems.
    """

    PRIMITIVES = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        type(None): {"type": "null"},
    }

    def __init__(self, service_manager):
        self.service_manager = service_manager
        self.type_defs: dict[str, dict] = {}  # Stores reusable type definitions
        self.processed_types: set[type] = set()  # Track processed types to avoid duplicates

    def _get_type_name(self, typ: type) -> str:
        """Get a unique name for a type."""
        if hasattr(typ, '__name__'):
            return typ.__name__
        return str(typ)

    def _process_type(self, typ: type) -> dict:
        """
        Process a type and return its JSON Schema representation.
        Complex types are added to type_defs and referenced via $ref.
        """
        # Handle None type
        if typ is type(None):
            return {"type": "null"}

        # Handle primitives
        if typ in self.PRIMITIVES:
            return self.PRIMITIVES[typ].copy()

        # Handle Optional types (Union[X, None])
        origin = get_origin(typ)
        if origin is type(None) or origin is type(None).__class__:
            return {"type": "null"}

        # Handle Union types
        if origin is Union or (hasattr(types, 'UnionType') and origin is types.UnionType):
            args = get_args(typ)
            # Check if it's Optional (Union with None)
            if type(None) in args:
                non_none_args = [arg for arg in args if arg is not type(None)]
                if len(non_none_args) == 1:
                    # This is Optional[X]
                    schema = self._process_type(non_none_args[0])
                    return {"anyOf": [schema, {"type": "null"}]}
            # Regular union
            return {"anyOf": [self._process_type(arg) for arg in args]}

        # Handle List/Sequence types
        if origin in (list, List) or (hasattr(collections.abc, 'Sequence') and origin is collections.abc.Sequence):
            args = get_args(typ)
            item_type = args[0] if args else Any
            return {
                "type": "array",
                "items": self._process_type(item_type)
            }

        # Handle Dict types
        if origin in (dict, Dict):
            args = get_args(typ)
            if len(args) >= 2:
                return {
                    "type": "object",
                    "additionalProperties": self._process_type(args[1])
                }
            return {"type": "object"}

        # Handle Pydantic models
        if isinstance(typ, type) and issubclass(typ, BaseModel):
            type_name = self._get_type_name(typ)

            # Add to type_defs if not already processed
            if typ not in self.processed_types:
                self.processed_types.add(typ)
                schema = typ.model_json_schema()
                # Remove $defs from individual schemas to avoid nesting
                if '$defs' in schema:
                    nested_defs = schema.pop('$defs')
                    self.type_defs.update(nested_defs)
                self.type_defs[type_name] = schema

            return {"$ref": f"#/$defs/{type_name}"}

        # Fallback for unknown types
        return {"type": "object", "description": f"Unknown type: {typ}"}

    def _extract_method_info(self, method_desc) -> dict:
        """Extract parameter and return type information from a method."""
        method_info = {
            "description": method_desc.method.__doc__ or "",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }

        # Process parameters
        for param in method_desc.params:
            if param.name == 'self':
                continue

            param_schema = self._process_type(param.type)
            method_info["parameters"]["properties"][param.name] = param_schema

            # Check if parameter is required (not Optional)
            origin = get_origin(param.type)
            args = get_args(param.type)
            is_optional = origin is Union and type(None) in args

            # Check if parameter has a default value
            has_default = hasattr(param, 'default') and param.default is not None

            if not is_optional and not has_default:
                method_info["parameters"]["required"].append(param.name)

        # If no required parameters, remove the empty list
        if not method_info["parameters"]["required"]:
            del method_info["parameters"]["required"]

        # Process return type
        if method_desc.return_type and method_desc.return_type is not type(None):
            method_info["returns"] = self._process_type(method_desc.return_type)
        else:
            method_info["returns"] = {"type": "null"}

        return method_info

    def generate(self) -> dict:
        """
        Generate a JSON Schema-based service descriptor.

        Returns a dictionary with:
        - services: Dictionary of service definitions
        - $defs: Reusable type definitions
        """
        schema = {
            "schemaVersion": "1.0.0",
            "services": {},
            "$defs": {}
        }

        for service_name, service in self.service_manager.descriptors_by_name.items():
            if service.is_component():
                continue

            descriptor = TypeDescriptor.for_type(service.type)

            service_schema = {
                "name": service_name,
                "type": self._get_type_name(service.type),
                "description": service.type.__doc__ or "",
                "methods": {}
            }

            # Process all methods
            for method_desc in descriptor.get_methods():
                method_name = method_desc.method.__name__

                # Skip private methods
                if method_name.startswith('_'):
                    continue

                service_schema["methods"][method_name] = self._extract_method_info(method_desc)

            schema["services"][service_name] = service_schema

        # Add all collected type definitions
        schema["$defs"] = self.type_defs

        return schema

    def to_json(self, indent: int = 2) -> str:
        """Generate and serialize the schema to JSON."""
        return json.dumps(self.generate(), indent=indent)


# Import required types
from typing import Union, List, Dict
import types
import collections.abc