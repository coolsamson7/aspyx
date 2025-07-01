"""
deserialization functions
"""
from dataclasses import is_dataclass, fields
from functools import lru_cache
from typing import get_origin, get_args, Union

from pydantic import BaseModel

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
    
class TypeSerializer:
    def __init__(self, typ):
        self.typ = typ
        self.serializer = self._build_serializer(typ)

    def __call__(self, value):
        return self.serializer(value)

    def _build_serializer(self, typ):
        origin = get_origin(typ)
        args = get_args(typ)

        if origin is Union:
            serializers = [TypeSerializer(arg) for arg in args if arg is not type(None)]
            def ser_union(value):
                if value is None:
                    return None
                for s in serializers:
                    try:
                        return s(value)
                    except Exception:
                        continue
                return value
            return ser_union

        if isinstance(typ, type) and issubclass(typ, BaseModel):
            return lambda v: v.dict() if v is not None else None

        if is_dataclass(typ):
            field_serializers = {f.name: TypeSerializer(f.type) for f in fields(typ)}
            def ser_dataclass(obj):
                if obj is None:
                    return None
                return {k: field_serializers[k](getattr(obj, k)) for k in field_serializers}
            return ser_dataclass

        if origin is list:
            item_ser = TypeSerializer(args[0]) if args else lambda x: x
            return lambda v: [item_ser(item) for item in v] if v is not None else None

        if origin is dict:
            key_ser = TypeSerializer(args[0]) if args else lambda x: x
            val_ser = TypeSerializer(args[1]) if len(args) > 1 else lambda x: x
            return lambda v: {key_ser(k): val_ser(val) for k, val in v.items()} if v is not None else None

        # Fallback: primitive Typen oder unbekannt
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

@lru_cache(maxsize=512)
def get_serializer(typ):
    """
    return a function that is able to deserialize a value of the specified type

    Args:
        typ: the type

    Returns:

    """
    return TypeSerializer(typ)
