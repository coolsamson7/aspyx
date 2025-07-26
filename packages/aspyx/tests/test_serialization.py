from dataclasses import dataclass
from lib2to3.btm_utils import pysyms

from pydantic import BaseModel

from aspyx.util import get_serializer, get_deserializer

@dataclass
class EmbeddedDataClass:
    name: str

embedded_dataclass = EmbeddedDataClass(name="foo")

class EmbeddedPydantic(BaseModel):
    name: str

embedded_pydantic = EmbeddedPydantic(name="foo")

@dataclass
class DataClass:
    int_attr : int
    bool_attr: bool
    int_list : list[int]

    embedded_dataclass : EmbeddedDataClass
    embedded_pydantic: EmbeddedPydantic

data_class = DataClass(int_attr=1, bool_attr=True, int_list=[1], embedded_pydantic=embedded_pydantic, embedded_dataclass=embedded_dataclass)

class Pydantic(BaseModel):
    int_attr: int
    bool_attr: bool

    int_list : list[int]

    embedded_dataclass: EmbeddedDataClass
    embedded_pydantic: EmbeddedPydantic

pydantic = Pydantic(int_attr=1, bool_attr=True,  int_list=[1], embedded_pydantic=embedded_pydantic, embedded_dataclass=embedded_dataclass)

class TestSerialization():
    def test_data_class(self):
        serializer = get_serializer(DataClass)
        deserializer = get_deserializer(DataClass)

        result = deserializer(serializer(data_class))

        assert data_class == result

    def test_pydantic(self):
        serializer = get_serializer(Pydantic)
        deserializer = get_deserializer(Pydantic)

        result = deserializer(serializer(pydantic))

        assert pydantic == result