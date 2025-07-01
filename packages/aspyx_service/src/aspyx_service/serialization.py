"""
deserialization functions
"""
from dataclasses import is_dataclass, fields
from functools import lru_cache
from typing import get_origin, get_args, Union

from pydantic import BaseModel

def deserialize(value, return_type):
    if value is None:
        return None

    origin = get_origin(return_type)
    args = get_args(return_type)

    # Handle Optional / Union
    if origin is Union and type(None) in args:
        real_type = [arg for arg in args if arg is not type(None)][0]
        return deserialize(value, real_type)

    # Handle pydantic
    if isinstance(return_type, type) and issubclass(return_type, BaseModel):
        return return_type.parse_obj(value)

    # Handle dataclass
    if is_dataclass(return_type):
        return from_dict(return_type, value)

    # Handle List[T]
    if origin is list:
        item_type = args[0]
        return [deserialize(v, item_type) for v in value]

    # Fallback: primitive
    return value

def from_dict(cls, data: dict):
    if not is_dataclass(cls):
        return data  # primitive or unknown

    kwargs = {}
    for field in fields(cls):
        name = field.name
        field_type = field.type
        value = data.get(name)

        if value is None:
            kwargs[name] = None
            continue

        origin = get_origin(field_type)
        args = get_args(field_type)

        if origin is Union and type(None) in args:
            real_type = [arg for arg in args if arg is not type(None)][0]
            kwargs[name] = deserialize(value, real_type)

        elif is_dataclass(field_type):
            kwargs[name] = from_dict(field_type, value)

        elif origin is list:
            item_type = args[0]
            kwargs[name] = [deserialize(v, item_type) for v in value]

        else:
            kwargs[name] = value

    return cls(**kwargs)

class TypeDeserializer:
    # constructor

    def __init__(self, typ):
        self.typ = typ
        self.deserializer = self._build_deserializer(typ)

    def __call__(self, value):
        return self.deserializer(value)

    # internal

    def _build_deserializer(self, typ):
        origin = get_origin(typ)
        args = get_args(typ)

        if origin is Union:
            deserializers = [TypeDeserializer(arg) for arg in args if arg is not type(None)]
            def deser_union(value):
                if value is None:
                    return None
                for d in deserializers:
                    try:
                        return d(value)
                    except Exception:
                        continue
                return value
            return deser_union

        if isinstance(typ, type) and issubclass(typ, BaseModel):
            return typ.parse_obj

        if is_dataclass(typ):
            field_deserializers = {f.name: TypeDeserializer(f.type) for f in fields(typ)}
            def deser_dataclass(value):
                return typ(**{
                    k: field_deserializers[k](v) for k, v in value.items()
                })
            return deser_dataclass

        if origin is list:
            item_deser = TypeDeserializer(args[0]) if args else lambda x: x
            return lambda v: [item_deser(item) for item in v]

        if origin is dict:
            key_deser = TypeDeserializer(args[0]) if args else lambda x: x
            val_deser = TypeDeserializer(args[1]) if len(args) > 1 else lambda x: x
            return lambda v: {key_deser(k): val_deser(val) for k, val in v.items()}

        # Fallback
        return lambda v: v

@lru_cache(maxsize=512)
def get_deserializer(typ):
    """
    return a function that is able to deserialize a value of the specified type

    Args:
        typ: the type

    Returns:

    """
    return TypeDeserializer(typ)
