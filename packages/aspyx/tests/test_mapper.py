import time
import unittest
from dataclasses import dataclass

from pydantic import BaseModel

from aspyx.mapper import Mapper, MappingDefinition, matching_properties, Convert
from aspyx.mapper.mapper import path
from aspyx.reflection import TypeDescriptor


class Class:
    id : str

    def __init__(self, id: str):
        self.id = id

@dataclass
class Money:
    currency : str
    value : int

@dataclass
class Product:
    name: str
    price: Money

@dataclass
class DataClass:
    id : str
    attr_1 : int
    attr_2 : int
    attr_3 : int
    attr_4 : int
    attr_5 : int
    attr_6 : int
    attr_7 : int
    attr_8 : int
    attr_9 : int

class Pydantic(BaseModel):
    id: str

@dataclass
class Types:
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

    dc = DataClass(id="id", attr_1=1,  attr_2=2, attr_3=3, attr_4=4, attr_5=5, attr_6=6, attr_7=7, attr_8=8, attr_9=9)

    p = Pydantic(id="id")

    types = Types(b=False, i=1, f=1.0, s="s")

    deep = Deep(
        dc=dc,
        dcs = [dc, dc, dc, dc, dc, dc, dc, dc, dc, dc]
    )

    product = Product(name="p", price=Money(currency="EUR", value=1))

    def test_class(self):
        d = TypeDescriptor.for_type(Class)
        mapper = Mapper(
            MappingDefinition(source=Class, target=Class)
                .map(from_="id", to="id")
        )

        res = mapper.map(TestMapper.c)
        self.assertEqual(res.id, TestMapper.c.id)

    def test_data_class(self):
        mapper = Mapper(
            MappingDefinition(source=DataClass, target=DataClass)
                .map(all=matching_properties())
        )

        res = mapper.map(TestMapper.dc)
        self.assertEqual(res.id, TestMapper.dc.id)

    def test_pydantic(self):
        mapper = Mapper(
            MappingDefinition(source=Pydantic, target=Pydantic)
                .map(from_="id", to="id")
        )

        res = mapper.map(TestMapper.p)
        self.assertEqual(res.id, TestMapper.p.id)

    def test_finalize(self):
        finalized = False

        def mark_finalized():
            nonlocal finalized
            finalized = True

        mapper = Mapper(
            MappingDefinition(source=DataClass, target=DataClass)
            .map(all=matching_properties())
            .finalize(lambda source, target: mark_finalized())
        )

        mapper.map(TestMapper.dc)
        self.assertTrue(finalized)

    def test_deep(self):
        mapper = Mapper(
            MappingDefinition(source=Deep, target=Deep)
                .map(from_="dc", to="dc", deep=True)
                .map(from_="dcs", to="dcs", deep=True),

            MappingDefinition(source=DataClass, target=DataClass)
                .map(all=matching_properties())
        )

        res = mapper.map(TestMapper.deep)
        print(res)

    def test_wildcards(self):
        mapper = Mapper(
            MappingDefinition(source=Types, target=Types)
                .map(all=matching_properties())
        )

        res = mapper.map(TestMapper.types)
        #self.assertEqual(res.id, TestMapper.c.id)

    def test_path(self): # TODO
        d1 = TypeDescriptor.for_type(Product)
        d2 = TypeDescriptor.for_type(Money)

        mapper = Mapper(
            MappingDefinition(source=Product, target=Product)
            .map(from_="name", to="name")
            .map(from_=path("price", "currency"), to=path("price", "currency"))
            .map(from_=path("price", "value"), to=path("price", "value"))
        )

        res = mapper.map(TestMapper.product)
        print(res)


    def test_conversion(self):
        mapper = Mapper(
            MappingDefinition(source=Types, target=Types)
                .map(from_="b", to="b", convert=Convert(bool, bool, convert_source=lambda s: not s))
                .map(from_="i", to="f")
                .map(from_="f", to="i")
                .map(from_="s", to="s", convert=Convert(str, str, convert_source=lambda s: s+s))
        )

        res = mapper.map(TestMapper.types)
        print(res)
        #self.assertEqual(res.id, TestMapper.c.id)

    def test_benchmark(self):
        mapper = Mapper(
            MappingDefinition(source=Deep, target=Deep)
                .map(from_="dc", to="dc", deep=True)
                .map(from_="dcs", to="dcs", deep=True),

            MappingDefinition(source=DataClass, target=DataClass)
                .map(all=matching_properties())
        )

        # warm up

        mapper.map(TestMapper.deep)

        # benchmark

        loops = 100000

        def map_manual():
            deep = TestMapper.deep

            def copy_dc(o : DataClass):
                return DataClass(id=o.id,
                                 attr_1=o.attr_1,
                                 attr_2=o.attr_1,
                                 attr_3=o.attr_1,
                                 attr_4=o.attr_1,
                                 attr_5=o.attr_1,
                                 attr_6=o.attr_1,
                                 attr_7=o.attr_1,
                                 attr_8=o.attr_1,
                                 attr_9=o.attr_1)
            Deep(
                dc=copy_dc(deep.dc),
                dcs = [copy_dc(x) for x in deep.dcs]
            )

        def map_operation():
            mapper.map(TestMapper.deep)

        measure(loops, map_manual, "manual")
        measure(loops, map_operation, "mapper")