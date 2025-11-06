from abc import ABC, abstractmethod
from typing import Any, Generic, List, TypeVar

CONTEXT = TypeVar("CONTEXT")

class Property(ABC, Generic[CONTEXT]):
    """
    A Property is able to read and write property values given an instance.

    CONTEXT: any context information that could be needed during a transformation
    """

    @abstractmethod
    def get(self, instance: Any, context: CONTEXT) -> Any:
        """Read a property value given an instance"""
        pass

    @abstractmethod
    def set(self, instance: Any, value: Any, context: CONTEXT) -> None:
        """Write a property value given an instance"""
        pass


class Operation(Generic[CONTEXT]):
    __slots__ = [
        "source",
        "target"
    ]

    """
    An Operation contains a source and a target Property that are used
    to read values from a source and set the result in the target object.
    """

    def __init__(self, source: Property[CONTEXT], target: Property[CONTEXT]):
        self.source = source
        self.target = target

    def set_target(self, from_: Any, to: Any, context: CONTEXT) -> None:
        """Set a target property by reading the appropriate value from the source"""
        value = self.source.get(from_, context)
        self.target.set(to, value, context)

    def set_source(self, to: Any, from_: Any, context: CONTEXT) -> None:
        """Set a source property by reading the appropriate value from the target"""
        value = self.target.get(to, context)
        self.source.set(from_, value, context)


class Transformer(Generic[CONTEXT]):
    """
    A Transformer is a generic class that transforms a source into a target object
    given a list of Operations.
    """

    __slots__ = [
        "operations"
    ]

    def __init__(self, operations: List[Operation[CONTEXT]]):
        self.operations = operations

    def transform_target(self, source: Any, target: Any, context: CONTEXT) -> None:
        for op in self.operations:
            op.set_target(source, target, context)
