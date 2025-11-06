import time
import unittest
from dataclasses import dataclass

from pydantic import BaseModel

from aspyx.mapper import Mapper, MappingDefinition, matching_properties
from aspyx.reflection import TypeDescriptor


class Class:
    id : str

    def __init__(self, id: str):
        self.id = id

@dataclass
class DataClass:
    id : str

class Pydantic(BaseModel):
    id: str

@dataclass
class Convert:
    b : bool
    i : int
    f : float
    s : str

@dataclass
class Deep:
    dc : DataClass
    dcs : list[DataClass]

def measure(n: int, func, name, *args, **kwargs):
    """
    Measure how long it takes to execute `func` n times.

    Args:
        n (int): number of iterations
        func (callable): the function to execute
        *args, **kwargs: arguments to pass to func
    """
    start = time.perf_counter()

    for _ in range(n):
        func(*args, **kwargs)

    end = time.perf_counter()

    total = end - start
    per_op = total / n if n > 0 else 0

    print(f"Total time for {name}: {total:.6f} seconds")
    print(f"Time per operation: {per_op * 1_000_000:.3f} µs ({per_op * 1000:.6f} ms)")


class TestMapper(unittest.TestCase):
    # instances

    c = Class(id="id")

    dc = DataClass(id="id")

    p = Pydantic(id="id")

    convert = Convert(b=False, i=1, f=1.0, s="s")

    deep = Deep(
        dc=dc,
        dcs = [dc]
    )

    def test_class(self):
        d = TypeDescriptor.for_type(Class)
        mapper = Mapper(
            MappingDefinition(source_class=Class, target_class=Class)
                .map(from_="id", to="id")
        )

        res = mapper.map(TestMapper.c)
        self.assertEqual(res.id, TestMapper.c.id)

    def test_data_class(self):
        mapper = Mapper(
            MappingDefinition(source_class=DataClass, target_class=DataClass)
                .map(from_="id", to="id")
        )

        res = mapper.map(TestMapper.dc)
        self.assertEqual(res.id, TestMapper.dc.id)

    def test_pydantic(self):
        mapper = Mapper(
            MappingDefinition(source_class=Pydantic, target_class=Pydantic)
                .map(from_="id", to="id")
        )

        res = mapper.map(TestMapper.p)
        self.assertEqual(res.id, TestMapper.p.id)

    def test_deep(self):
        mapper = Mapper(
            MappingDefinition(source_class=Deep, target_class=Deep)
                .map(from_="dc", to="dc", deep=True),
                #.map(from_="dcs", to="dcs", deep=True),

            MappingDefinition(source_class=DataClass, target_class=DataClass)
                .map(from_="id", to="id")
        )

        res = mapper.map(TestMapper.deep)

    def test_wildcards(self):
        mapper = Mapper(
            MappingDefinition(source_class=Convert, target_class=Convert)
                .map(all=matching_properties())
        )

        res = mapper.map(TestMapper.convert)
        #self.assertEqual(res.id, TestMapper.c.id)

    def test_conversion(self):
        mapper = Mapper(
            MappingDefinition(source_class=Convert, target_class=Convert)
                .map(from_="b", to="b")
                .map(from_="i", to="f")
                .map(from_="f", to="i")
                .map(from_="s", to="s")
        )

        res = mapper.map(TestMapper.convert)
        #self.assertEqual(res.id, TestMapper.c.id)

    def test_benchmark(self):
        mapper = Mapper(
            MappingDefinition(source_class=Deep, target_class=Deep)
                .map(from_="dc", to="dc", deep=True),
                #.map(from_="dcs", to="dcs", deep=True),

            MappingDefinition(source_class=DataClass, target_class=DataClass)
                .map(from_="id", to="id")
        )

        # warm up

        res = mapper.map(TestMapper.deep)

        # benchmark

        loops = 100000

        def map_manual():
            copy = DataClass(id=TestMapper.dc.id)
            list_copy = [DataClass(id=TestMapper.dc.id)]
            result = Deep(
                dc=copy,
                dcs = list_copy
            )

        def map_operation():
            mapper.map(TestMapper.deep)

        measure(loops, map_manual, "manual")
        measure(loops, map_operation, "mapper")