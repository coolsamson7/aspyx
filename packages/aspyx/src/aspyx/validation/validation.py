from __future__ import annotations
from typing import Any, Callable, Type, TypeVar, Generic, Dict, List, Optional
from enum import Enum
import re

T = TypeVar('T')
B = TypeVar('B', bound='AbstractType')

# --- Helper Type Aliases ---
Check = Callable[[T], bool]
MethodApplier = Callable[['AbstractType', list[Any]], None]

# --- ArgType Enum ---
class ArgType(Enum):
    STRING = 'stringType'
    INT = 'intType'
    DOUBLE = 'doubleType'

    def parse(self, value: str) -> Any:
        if self is ArgType.STRING:
            return value
        elif self is ArgType.INT:
            return int(value)
        elif self is ArgType.DOUBLE:
            return float(value)

    @property
    def name(self) -> str:
        return self.value

# --- Test ---
class Test(Generic[T]):
    def __init__(self, *, type_: Type, name: str, check: Check[T],
                 params: Optional[Dict[str, Any]] = None,
                 stop: bool = False, message: Optional[str] = None):
        self.type = type_
        self.name = name
        self.check = check
        self.params = params or {}
        self.stop = stop
        self.message = message

    def run(self, obj: Any) -> bool:
        try:
            return self.check(obj)
        except Exception:
            return False

# --- MethodSpec ---
class MethodSpec:
    def __init__(self, arg_count: int, arg_types: List[ArgType], apply: MethodApplier):
        self.arg_count = arg_count
        self.arg_types = arg_types
        self.apply = apply

# --- Validation System ---
class TypeViolation:
    def __init__(self, *, type_: Type, name: str, params: Dict[str, Any],
                 value: Any, path: str, message: str):
        self.type = type_
        self.name = name
        self.params = params
        self.value = value
        self.path = path
        self.message = message

    def __str__(self):
        return f"[{self.path}] {self.name} failed on {self.value} ({self.message})"

class ValidationContext:
    def __init__(self):
        self.violations: List[TypeViolation] = []
        self.path: str = ""

    def add_violation(self, *, type_: Type, name: str, params: Dict[str, Any],
                      value: Any, path: str, message: str = ""):
        self.violations.append(TypeViolation(
            type_=type_, name=name, params=params, value=value,
            path=path, message=message
        ))

    @property
    def has_violations(self) -> bool:
        return bool(self.violations)

class ValidationException(Exception):
    def __init__(self, violations: List[TypeViolation]):
        self.violations = violations
        super().__init__(str(self))

    def __str__(self):
        return "\n".join(str(v) for v in self.violations)

# --- AbstractType Base ---
class AbstractType(Generic[T, B]):
    def __init__(self, *, type_: Type):
        self.type = type_
        self.nullable = False
        self.tests: List[Test[Any]] = []

    def base_type(self, type_: Type):
        self.type = type_
        self.test(
            type_=type_,
            name="type",
            params={"type": type_},
            check=lambda obj: (obj is None and self.nullable) or isinstance(obj, type_),
            stop=True
        )

    def test(self, *, type_: Type, name: str, check: Check[Any],
             params: Optional[Dict[str, Any]] = None,
             stop: bool = False, message: Optional[str] = None) -> B:
        self.tests.append(Test(type_=type_, name=name, check=check,
                               params=params, stop=stop, message=message))
        return self  # type: ignore

    def check_value(self, obj: Any, context: ValidationContext):
        for test in self.tests:
            if not test.run(obj):
                context.add_violation(
                    type_=test.type,
                    name=test.name,
                    params=test.params,
                    path=context.path,
                    value=obj,
                    message=test.message or ""
                )
                if test.stop:
                    break

    def validate(self, obj: Any):
        context = ValidationContext()
        self.check_value(obj, context)
        if context.has_violations:
            raise ValidationException(context.violations)

    def is_valid(self, obj: Any) -> bool:
        context = ValidationContext()
        self.check_value(obj, context)
        return not context.has_violations

    def optional(self) -> B:
        self.nullable = True
        if self.tests:
            self.tests[0].stop = True
        return self  # type: ignore

    def required(self) -> B:
        self.nullable = False
        return self  # type: ignore

# --- Concrete Implementations ---
class IntType(AbstractType[int, 'IntType']):
    def __init__(self):
        super().__init__(type_=int)
        self.base_type(int)

    def min(self, value: int) -> 'IntType':
        return self.test(type_=int, name="min", params={"min": value}, check=lambda x: x >= value)

    def max(self, value: int) -> 'IntType':
        return self.test(type_=int, name="max", params={"max": value}, check=lambda x: x <= value)

    def less_than(self, value: int) -> 'IntType':
        return self.test(type_=int, name="lessThan", params={"lessThan": value}, check=lambda x: x < value)

    def greater_than(self, value: int) -> 'IntType':
        return self.test(type_=int, name="greaterThan", params={"greaterThan": value}, check=lambda x: x > value)

class DoubleType(AbstractType[float, 'DoubleType']):
    def __init__(self):
        super().__init__(type_=float)
        self.base_type(float)

    def min(self, value: float) -> 'DoubleType':
        return self.test(type_=float, name="min", params={"min": value}, check=lambda x: x >= value)

    def max(self, value: float) -> 'DoubleType':
        return self.test(type_=float, name="max", params={"max": value}, check=lambda x: x <= value)

class StringType(AbstractType[str, 'StringType']):
    def __init__(self):
        super().__init__(type_=str)
        self.base_type(str)

    def not_empty(self) -> 'StringType':
        return self.test(type_=str, name="notEmpty", check=lambda s: bool(s and len(s) > 0))

    def min_length(self, length: int) -> 'StringType':
        return self.test(type_=str, name="minLength", params={"minLength": length}, check=lambda s: len(s) >= length)

    def max_length(self, length: int) -> 'StringType':
        return self.test(type_=str, name="maxLength", params={"maxLength": length}, check=lambda s: len(s) <= length)

    def re(self, pattern: str, message: Optional[str] = None) -> 'StringType':
        regex = re.compile(pattern)
        return self.test(type_=str, name="re", check=lambda s: bool(regex.match(s)), message=message)

class BoolType(AbstractType[bool, 'BoolType']):
    def __init__(self):
        super().__init__(type_=bool)
        self.base_type(bool)

# --- List Type ---
class ListType(AbstractType[list, 'ListType']):
    def __init__(self, element_type: AbstractType):
        super().__init__(type_=list)
        self.element_type = element_type
        self.test(type_=list, name="type", check=lambda obj: isinstance(obj, list), stop=True)

    def min(self, length: int) -> 'ListType':
        return self.test(type_=list, name="min", params={"min": length}, check=lambda s: len(s) >= length)

    def max(self, length: int) -> 'ListType':
        return self.test(type_=list, name="max", params={"max": length}, check=lambda s: len(s) <= length)


# some constants

def string():
    return StringType()

def boolean():
    return BoolType()

def integer():
    return IntType()

def double():
    return DoubleType()
