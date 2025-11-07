from dataclasses import dataclass
from typing import Optional, Type, Callable, Any, Dict, Tuple, TypeVar, Generic

Converter = Callable[[Any], Any]

S = TypeVar('S')
T = TypeVar('T')

class Convert(Generic[S, T]):
    def __init__(self, source_type: type[S], target_type: type[T], convert_source: Callable[[S], T], convert_target: Optional[Callable[[T], S]] = None):
        self.source_type = source_type
        self.target_type = target_type
        self.convert_source_func= convert_source
        self.convert_target_func= convert_target

    def convert_source(self, source: S) -> T:
        if self.convert_source_func is None:
            raise Exception("No convert_source function")

        return self.convert_source_func(source)

    def convert_target(self, source: T) -> S:
        if self.convert_target_func is None:
            raise Exception("No convert_target function")

        return self.convert_target_func(source)

    def source_converter(self):
        return lambda s: self.convert_source(s)

    def target_converter(self):
        return lambda s: self.convert_target(s)

class TypeConversions:
    def __init__(self):
        self._converters: Dict[Tuple[Type, Type], Converter] = {
            (str, int): lambda v: int(v) if v is not None else None,
            (str, float): lambda v: float(v) if v is not None else None,
            (str, bool): lambda v: str(v).lower() == 'true',
            (bool, int): lambda v: 1 if v else 0,
            (bool, float): lambda v: 1.0 if v else 0.0,
            (int, str): lambda v: str(v),
            (float, str): lambda v: str(v),
            (int, float): lambda v: float(v),
            (float, int): lambda v: int(v),
            (int, bool): lambda v: v == 1,
            (float, bool): lambda v: v == 1.0,
        }

    def register(self, convert: Convert):
        key = (convert.source_type, convert.target_type)
        self._converters[key] = convert.source_converter()

    def get_converter(self, from_type: Type, to_type: Type) -> Optional[Converter]:
        return self._converters.get((from_type, to_type))

    def convert(self, value, from_type: Type, to_type: Type):
        if value is None or from_type == to_type:
            return value
        converter = self._converters.get((from_type, to_type))
        if converter:
            return converter(value)
        if type(value) == to_type:
            return value
        raise TypeError(f"No converter registered for {from_type} -> {to_type}")