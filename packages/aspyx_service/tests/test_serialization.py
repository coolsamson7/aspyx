"""
serialization tests
"""
from dataclasses import dataclass

from pydantic import BaseModel

from aspyx.util import get_deserializer, get_serializer

class Pydantic(BaseModel):
    i : int
    f : float
    b: bool
    s: str

@dataclass
class Data:
    i: int
    f: float
    b: bool
    s: str

class PydanticAndData(BaseModel):
    data: Data

@dataclass
class DataAndPydantic:
    pydantic: Pydantic

pydantic = Pydantic(i=1, f=1.0, b=True, s="s")
data = Data(i=1, f=1.0, b=True, s="s")

p_plus_d = PydanticAndData(data=data)
d_plus_p = DataAndPydantic(pydantic=pydantic)

class TestSerialization:
    def test_pydantic(self):
        serializer = get_serializer(Pydantic)
        deserializer = get_deserializer(Pydantic)

        output = serializer(pydantic)
        reverse = deserializer(output)

        assert reverse == pydantic

    def test_data(self):
        serializer = get_serializer(Data)
        deserializer = get_deserializer(Data)

        output = serializer(data)
        reverse = deserializer(output)

        assert reverse == data

    def test_pydantic_plus_data(self):
        serializer = get_serializer(PydanticAndData)
        deserializer = get_deserializer(PydanticAndData)

        output = serializer(p_plus_d)
        reverse = deserializer(output)

        assert p_plus_d == reverse

    def test_data_plus_pydantic(self):
        serializer = get_serializer(DataAndPydantic)
        deserializer = get_deserializer(DataAndPydantic)

        output = serializer(d_plus_p)
        reverse = deserializer(output)

        assert reverse == d_plus_p
