"""

"""
from abc import ABC, abstractmethod
from typing import Any, Callable, List, Optional, Type, get_origin, get_args, Union
from dataclasses import dataclass

from .convert import TypeConversions
from ..reflection.reflection import TypeDescriptor
from .transformer import Operation, Property

class MapperException(Exception):
    pass


class MapperProperty(Property["MappingContext"], ABC):
    """
    MapperProperty is a Property that can provide type information and optional validation.
    """

    @abstractmethod
    def get_type(self) -> type:
        """
        Return the type of the property.
        """
        pass

    def validate(self, value: Any) -> None:
        """
        Optional validation of the value. Default does nothing.
        Override in subclasses if validation is needed.
        """
        pass

class MapperPropertyd:
    def get(self, instance: Any, context: Any):
        raise NotImplementedError
    def set(self, instance: Any, value: Any, context: Any):
        raise NotImplementedError
    def get_type(self) -> Type:
        return object

class MapList2List(MapperProperty):
    def __init__(self, mapper, source_type: Type, target_type: Type, property: MapperProperty, factory: Callable):
        self.mapper = mapper
        self.source_type = source_type
        self.target_type = target_type
        self.property = property
        self.factory = factory
        self.mapping = None
        self.polymorphic = False
        #TODO if TypeDescriptor.has_type_static(source_type):
        self.polymorphic = False#bool(TypeDescriptor.for_type(source_type).child_classes()) TODO

    def set(self, instance, value, context):
        if value is None:
            return

        lst = list(value)
        result = self.factory()
        if self.polymorphic:
            for element in lst:
                mapping = self.mapper.get_source_mapping(type(element))
                result.append(self.mapper.map(element, context=context, mapping=mapping))
        else:
            if self.mapping is None:
                self.mapping = self.mapper.get_mapping_x(self.source_type, self.target_type)
            for element in lst:
                result.append(self.mapper.map(element, context=context, mapping=self.mapping))
        self.property.set(instance, result, context)

    def get(self, instance, context):
        return None

    def get_type(self):
        return self.property.get_type()

class MapDeep(MapperProperty):
    def __init__(self, mapper, source_type: Type, target_property: MapperProperty):
        self.mapper = mapper
        self.source_type = source_type
        self.target_property = target_property
        self.mapping = None
        self.polymorphic = False
        #TODOif TypeDescriptor.has_type_static(source_type):
        self.polymorphic = False#bool(TypeDescriptor.for_type(source_type).child_classes())

    def get(self, instance, context):
        return None

    def set(self, instance, value, context):
        if self.polymorphic:
            mapping = self.mapper.get_source_mapping(type(value))
            self.target_property.set(instance, self.mapper.map(value, context=context, mapping=mapping), context)
        else:
            if self.mapping is None:
                self.mapping = self.mapper.get_mapping_x(self.source_type, self.target_property.get_type())
            self.target_property.set(instance, self.mapper.map(value, context=context, mapping=self.mapping), context)

    def get_type(self):
        return self.target_property.get_type()

class ConvertProperty(MapperProperty):
    def __init__(self, property: MapperProperty, conversion: Callable):
        self.property = property
        self.conversion = conversion

    def get(self, instance, context):
        return self.conversion(self.property.get(instance, context))

    def set(self, instance, value, context):
        self.property.set(instance, self.conversion(value), context)

    def get_type(self):
        return object

class SetResultArgument(MapperProperty):
    def __init__(self, result_definition, index: int, property: MapperProperty):
        self.result_definition = result_definition
        self.index = index
        self.property = property
        self.result_definition.missing -= 1

    def get(self, instance, context):
        raise MapperException("wrong direction")

    def set(self, instance, value, context):
        if hasattr(self.property, 'validate'):
            try:
                self.property.validate(value)
            except Exception:
                pass
        context.get_result_buffer(self.result_definition.index).set(instance, value, self.property, self.index, context)

    def get_type(self):
        if self.index < self.result_definition.constructor_args:
            return self.result_definition.type_descriptor.constructor_parameters()[self.index].type
        else:
            return self.property.get_type()

class PeekValueProperty(MapperProperty):
    def __init__(self, index: int, property: MapperProperty):
        self.index = index
        self.property = property

    def get(self, instance, context):
        value = context.peek(self.index)
        if value is not None:
            return self.property.get(value, context)
        return None

    def set(self, instance, value, context):
        raise MapperException("not possible")

    def get_type(self):
        return self.property.get_type()

class PushValueProperty(MapperProperty):
    def __init__(self, index: int):
        self.index = index

    def get(self, instance, context):
        raise MapperException("not possible")

    def set(self, instance, value, context):
        context.push(value, self.index)

    def get_type(self):
        return object

# Value receivers

class ValueReceiver:
    def receive(self, context, instance, value):
        raise NotImplementedError

class SetPropertyValueReceiver(ValueReceiver):
    def __init__(self, property: MapperProperty):
        self.property = property
    def receive(self, context, instance, value):
        self.property.set(instance, value, context)

class SetResultPropertyValueReceiver(ValueReceiver):
    def __init__(self, result_index: int, index: int, property: Optional[MapperProperty]):
        self.result_index = result_index
        self.index = index
        self.property = property
    def receive(self, context, instance, value):
        context.get_result_buffer(self.result_index).set(instance, value, self.property, self.index, context)

class MappingResultValueReceiver(ValueReceiver):
    def receive(self, context, instance, value):
        if getattr(context, "current_state", None) is not None:
            context.current_state.result = value

# Source/Target trees, Buffer, IntermediateResultDefinition, OperationBuilder

class SourceNode:
    def __init__(self, accessor, match=None, parent=None):
        self.parent = parent
        self.accessor = accessor
        self.match = match
        self.children: List[SourceNode] = []
        self.stack_index = -1
        self.fetch_property: Optional[MapperProperty] = None
        self.type = accessor.type if hasattr(accessor, 'type') else object

    @property
    def is_root(self):
        return self.parent is None

    @property
    def is_leaf(self):
        return len(self.children) == 0

    def fetch_value(self, source_tree, expected_type, operations):
        if not self.is_root:
            self.parent.fetch_value(source_tree, expected_type, operations)

        if self.fetch_property is None:
            if self.is_root:
                self.fetch_property = self.accessor.make_transformer_property(False)
                self.type = self.accessor.type
            else:
                self.fetch_property = PeekValueProperty(index=self.parent.stack_index,
                                                        property=self.accessor.make_transformer_property(False))
                self.type = self.accessor.type
            if not self.is_leaf:
                self.stack_index = source_tree.stack_size
                source_tree.stack_size += 1
                operations.append(Operation(self.fetch_property, PushValueProperty(index=self.stack_index)))

    def insert_match(self, tree, match, index):
        root = next((c for c in self.children if c.accessor == match.paths[0][index]), None)
        if root is None:
            root = tree.make_node(self, match.paths[0][index], match if (len(match.paths[0]) - 1 == index) else None)
            self.children.append(root)
        if len(match.paths[0]) > index + 1:
            root.insert_match(tree, match, index + 1)

    def find_matching_node(self, match, index):
        if index < len(match.paths[0]):
            for child in self.children:
                if child.accessor == match.paths[0][index]:
                    return child.find_matching_node(match, index + 1)
        return self

class SourceTree:
    def __init__(self, typ, matches):
        self.roots: List[SourceNode] = []
        self.stack_size = 0
        self.type = typ
        for match in matches:
            self.insert_match(match)

    def insert_match(self, match):
        root = next((r for r in self.roots if r.accessor == match.paths[0][0]), None)
        if root is None:
            root = self.make_node(None, match.paths[0][0], match if len(match.paths[0]) == 1 else None)
            self.roots.append(root)
        if len(match.paths[0]) > 1:
            root.insert_match(self, match, 1)

    def find_node(self, match):
        for node in self.roots:
            if node.match == match:
                return node
            elif node.accessor == match.paths[0][0]:
                return node.find_matching_node(match, 1)
        return None

    def make_node(self, parent, accessor, match):
        accessor.resolve(parent.accessor.type if parent else self.type, False)
        return SourceNode(accessor=accessor, parent=parent, match=match)

class Buffer:
    def __init__(self, definition, n_args, constructor_args):
        constructor_args = n_args # TODO WTF
        ###
        self.definition = definition
        self.n_args = n_args
        self.constructor_args = constructor_args
        self.constructor = definition.constructor
        self.value_receiver = definition.value_receiver
        self.n_supplied_args = 0
        self.arguments = {}
        #self.array_arguments = [None] * constructor_args
        self.result = None
        if constructor_args == 0:
            self.result = self.constructor({})

    def set(self, instance, value, property, index, mapping_context):
        if self.n_supplied_args < self.constructor_args:
            #self.array_arguments[index] = value
            self.arguments[property.name] = value
            if self.n_supplied_args == self.constructor_args - 1:
                self.result = self.constructor(**self.arguments)
        else:
            property.set(self.result, value, mapping_context)
        self.n_supplied_args += 1
        if self.n_supplied_args == self.n_args:
            self.value_receiver.receive(mapping_context, instance, self.result)

class IntermediateResultDefinition:
    def __init__(self, type_descriptor: TypeDescriptor, constructor, index, n_args, value_receiver):
        self.type_descriptor = type_descriptor
        self.constructor = constructor
        self.index = index
        self.n_args = n_args
        self.value_receiver = value_receiver
        self.constructor_args = len(type_descriptor.properties)# TODO len(type_descriptor.constructor_parameters)
        self.missing = self.constructor_args

    def create_buffer(self):
        return Buffer(self, self.n_args, self.constructor_args)

type_conversions = TypeConversions()

class TargetNode:
    def __init__(self, accessor, match=None, parent=None):
        self.parent = parent
        self.accessor = accessor
        self.match = match
        self.children: List[TargetNode] = []
        self.stack_index = -1
        self.result_definition: Optional[IntermediateResultDefinition] = None
        self.fetch_property: Optional[MapperProperty] = None
        self.type = accessor.type

    @property
    def is_root(self):
        return self.parent is None

    @property
    def is_leaf(self):
        return len(self.children) == 0

    @property
    def is_inner_node(self):
        return len(self.children) > 0

    def compute_value_receiver(self):
        if self.parent and self.parent.result_definition is not None:
            self.parent.result_definition.missing -= 1
            return SetResultPropertyValueReceiver(
                result_index=self.parent.result_definition.index,
                index=self.accessor.index,
                property=self.accessor.make_transformer_property(True) #TODO if self.accessor.index >= self.parent.result_definition.constructor_args else None)
            )
        else:
            return SetPropertyValueReceiver(property=self.accessor.make_transformer_property(True))

    def try_convert(self, source_type, target_type):
        conv = type_conversions.get_converter(source_type, target_type)
        if conv is not None:
            return conv
        raise MapperException(f"cannot convert {source_type} to {target_type}")

    def normalize_type(self, t):
        origin = get_origin(t)
        if origin is Union:
            args = get_args(t)
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return non_none[0]
        return t

    def calculate_conversion(self, source_node):
        conversion = self.match.operation.converter
        deep = self.match.operation.deep
        result = None
        source_type = source_node.accessor.type
        target_type = self.accessor.type
        if conversion is not None:
            from_type = conversion.source_type
            to_type = conversion.target_type
            if from_type != source_type:
                raise MapperException(f"conversion source type {from_type} does not match {source_type}")
            if to_type != target_type:
                raise MapperException(f"conversion target type {to_type} does not match {target_type}")
            result = conversion.source_converter()
        elif source_type != target_type and not deep:
            if self.normalize_type(source_type) != self.normalize_type(target_type):
                result = self.try_convert(source_type, target_type)
        return result

    def maybe_convert(self, prop: MapperProperty, conversion):
        if conversion is None:
            return prop
        return ConvertProperty(property=prop, conversion=conversion)

    def map_deep(self, mapper, source_accessor, target_accessor, target_property):
        is_source_multi = source_accessor.is_container()
        is_target_multi = target_accessor.is_container()
        if is_source_multi != is_target_multi:
            raise MapperException("relations must have the same cardinality")
        if is_source_multi:
            return MapList2List(mapper=mapper,
                                source_type=source_accessor.get_element_type(),
                                target_type=target_accessor.get_element_type(),
                                property=target_property,
                                factory=target_accessor.get_container_constructor())
        else:
            return MapDeep(mapper=mapper, source_type=source_accessor.type, target_property=target_property)

    def make_operation(self, source_node, mapper):
        source_property = source_node.fetch_property
        deep = self.match.operation.deep
        conversion = self.calculate_conversion(source_node)
        requires_write = self.parent and self.parent.result_definition is None
        write_property = self.accessor.make_transformer_property(requires_write)
        if self.parent and self.parent.result_definition is not None:
            self.parent.result_definition.missing -= 1
            write_property = SetResultArgument(self.parent.result_definition, self.accessor.index, write_property)
        if deep:
            write_property = self.map_deep(mapper, source_node.accessor, self.accessor, write_property)
        else:
            write_property = self.maybe_convert(write_property, conversion)
        return Operation(source_property, write_property)

    def make_operations(self, source_tree, target_tree, mapper, definition, operations):
        typ = self.accessor.type
        if self.is_root:
            descriptor = TypeDescriptor.for_type(target_tree.type)
            if descriptor.is_immutable() or not descriptor.has_default_constructor():
                self.result_definition = definition.add_intermediate_result_definition(TypeDescriptor.for_type(typ), descriptor.constructor, len(self.children), MappingResultValueReceiver())
            for child in self.children:
                child.make_operations(source_tree, target_tree, mapper, definition, operations)
        elif self.is_inner_node:
            descriptor = TypeDescriptor.for_type(typ)
            value_receiver = self.compute_value_receiver()
            constructor = descriptor.constructor
            self.result_definition = definition.add_intermediate_result_definition(descriptor, constructor, len(self.children), value_receiver)
            for child in self.children:
                child.make_operations(source_tree, target_tree, mapper, definition, operations)
        else:
            source_node = source_tree.find_node(self.match)
            source_node.fetch_value(source_tree, typ, operations)
            operations.append(self.make_operation(source_node, mapper))

    def insert_match(self, tree, match, index):
        root = next((c for c in self.children if c.accessor == match.paths[1][index]), None)
        if root is None:
            root = tree.make_node(self, match.paths[1][index], match if (len(match.paths[1]) - 1 == index) else None)
            self.children.append(root)
        if len(match.paths[1]) > index + 1:
            root.insert_match(tree, match, index + 1)

    def find_matching_node(self, match, index):
        if index < len(match.paths[0]):
            for child in self.children:
                if child.accessor == match.paths[0][index]:
                    return child.find_matching_node(match, index + 1)
        return self

class RootAccessor:
    def __init__(self, typ):
        self.name = ""
        self.type = typ
        self.index = 0
        self.read_only = False

    def make_transformer_property(self, write):
        raise NotImplementedError

    def resolve(self, typ, write):
        pass

    def __eq__(self, other):
        return isinstance(other, RootAccessor)

    def __hash__(self):
        return 1

class TargetTree:
    def __init__(self, typ, matches):
        self.root = TargetNode(accessor=RootAccessor(typ), parent=None, match=None)
        self.stack_size = 0
        self.type = typ
        for match in matches:
            self.root.insert_match(self, match, 0)

    def make_operations(self, source_tree, mapper, definition):
        operations = []
        self.root.make_operations(source_tree, self, mapper, definition, operations)
        return operations

    def make_node(self, parent, accessor, match):
        accessor.resolve(parent.accessor.type if parent else self.type, False)
        return TargetNode(accessor=accessor, parent=parent, match=match)

@dataclass
class OperationResult:
    operations: List[Operation]
    constructor: Callable
    stack_size: int

class OperationBuilder:
    def __init__(self, matches):
        self.matches = matches

    def make_operations(self, mapper, definition):
        source_tree = SourceTree(definition.source_class, self.matches)
        target_tree = TargetTree(definition.target_class, self.matches)
        operations = target_tree.make_operations(source_tree, mapper, definition)
        constructor = target_tree.root.result_definition.constructor if target_tree.root.result_definition else None

        type_descriptor = TypeDescriptor.for_type(definition.target_class)
        if constructor is None:
            constructor = type_descriptor.constructor#get_constructor()
        return OperationResult(operations=operations, constructor=constructor or (lambda: None), stack_size=source_tree.stack_size)
