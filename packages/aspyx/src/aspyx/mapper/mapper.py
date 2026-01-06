"""

"""

from typing import Any, Callable, Dict, List, Optional, Tuple, Type, TypeVar, Generic
from dataclasses import dataclass

from .convert import Convert
from .operation_builder import MapperException, MapperProperty, IntermediateResultDefinition, OperationBuilder
from .transformer import Transformer
from ..reflection.reflection import TypeDescriptor, is_list_type, get_list_element_type

S = TypeVar("S")  # Source type
T = TypeVar("T")  # Target type

# Property implementations used by Accessors


def make_setter(cls: Type, field_name: str) -> Callable[[Any, Any], None]:
    attr = getattr(cls, field_name, None)

    # If it's a property with a fset, call that directly
    if isinstance(attr, property) and attr.fset:
        fset = attr.fset
        def setter(instance: Any, value: Any):
            fset(instance, value)
        return setter

    # Default: setattr
    def setter(instance: Any, value: Any):
        setattr(instance, field_name, value)

    return setter

class PropertyProperty:
    def __init__(self, field: TypeDescriptor.PropertyDescriptor, model_class=None):
        """
        :param field: A descriptor that should have a 'name' attribute.
        :param model_class: Optional Pydantic model class to check fields from.
        """
        self.field = field
        self.name = getattr(field, "name", None)
        self.getter = getattr(field, "getter", lambda obj: getattr(obj, self.name))
        self._setter_func = make_setter(field.clazz, field.name)
        self.model_class = model_class  # Needed to inspect Pydantic model_fields

    def get(self, instance, context=None):
        return self.getter(instance)

    def set(self, instance, value, context=None):
        result = self._setter_func(instance, value)
        # For frozen models, setter returns new instance, otherwise None
        return result if result is not None else instance

    def get_type(self):
        return getattr(self.field, "type", object)

class ValidatingPropertyProperty(PropertyProperty):
    def __init__(self, field):
        super().__init__(field)
        self.type_info = getattr(field, 'type', None)

    def set(self, instance, value, context):
        if hasattr(self.type_info, 'validate'):
            self.type_info.validate(value)
        super().set(instance, value, context)

    def get_type(self):
        return getattr(self.type_info, 'type', object)

class ConstantValue(MapperProperty):
    __slots__ = [
        "value"
    ]

    def __init__(self, value):
        self.value = value

    def get(self, instance, context):
        return self.value

    def set(self, instance, value, context):
        pass

    def get_type(self):
        return type(self.value)

# Accessor base classes

class Accessor:
    def __init__(self, name: str, typ: Type, index: int, read_only: bool=False):
        self.name = name
        self.index = index
        self.read_only = read_only
        self.type = typ
        # mapper will be set by context when needed
        self.mapper = None

    def resolve(self, typ: Type, write: bool):
        raise NotImplementedError

    def make_transformer_property(self, write: bool) -> MapperProperty:
        raise NotImplementedError

    def is_container(self):
        return is_list_type(self.type)

    def get_element_type(self):
        return get_list_element_type(self.type)

    def get_container_constructor(self):
        return list if self.is_container() else None # TODO just list now

class ConstantAccessor(Accessor):
    def __init__(self, value):
        super().__init__(name=str(value), typ=type(value), index=0, read_only=True)
        self.value = value

    def resolve(self, typ: Type, write: bool):
        if write:
            raise MapperException("constants are not writeable")

    def make_transformer_property(self, write: bool) -> MapperProperty:
        if write:
            raise MapperException("constants are not writeable")
        return ConstantValue(self.value)

    def __eq__(self, other):
        return isinstance(other, ConstantAccessor) and self.value == other.value

    def __hash__(self):
        return hash(self.value) if self.value is not None else 0

class PropertyAccessor(Accessor):
    def __init__(self, name: str, validate: bool=False):
        super().__init__(name=name, typ=object, index=-1, read_only=False)
        self.validate = validate
        self.field = None

    def make_transformer_property(self, write: bool):
        if write:
            if self.field is None:
                raise MapperException("field not resolved")
            if getattr(self.field, 'is_writeable', lambda: True)():
                return ValidatingPropertyProperty(self.field) if self.validate else PropertyProperty(self.field)
            else:
                raise MapperException(f"{self.field.type_descriptor.type}.{self.name} is final")
        else:
            return ValidatingPropertyProperty(self.field) if self.validate else PropertyProperty(self.field)

    #def get_container_constructor(self):
    #    return getattr(self.field, 'factory_constructor', None)

    #def get_element_type(self):
    #    return getattr(self.field, 'element_type', getattr(self.field, 'type', object))

    def resolve(self, typ: Type, write: bool):
        descriptor = TypeDescriptor.for_type(typ)
        init = descriptor.get_method("__init__")
        if init is not None:
            params = init.params
            idx = next((i for i, p in enumerate(params) if p.name == self.name), -1)
            self.index = idx
        else:
            self.index = -1

        self.field = descriptor.get_property(self.name)
        self.type = getattr(self.field, 'type', object)

    def __eq__(self, other):
        return isinstance(other, PropertyAccessor) and self.name == other.name

    def __hash__(self):
        return hash(self.name)

# MapOperation classes and qualifiers

class MapOperation:
    def __init__(self, converter: Optional[Convert]=None, deep: bool=False):
        self.converter = converter
        self.deep = deep
    def find_matches(self, definition, matches):
        raise NotImplementedError

class PropertyQualifier:
    def compute_properties(self, source_class: Type, target_class: Type) -> List[str]:
        raise NotImplementedError

class Properties(PropertyQualifier):
    def __init__(self, properties: List[str]):
        self.properties = properties
    def compute_properties(self, source_class: Type, target_class: Type) -> List[str]:
        return self.properties

class AllProperties(PropertyQualifier):
    def __init__(self):
        self.exceptions: List[str] = []
    def except_properties(self, properties: List[str]):
        self.exceptions.extend(properties)
        return self
    def compute_properties(self, source_class: Type, target_class: Type) -> List[str]:
        result = []
        src_desc = TypeDescriptor.for_type(source_class)
        tgt_desc = TypeDescriptor.for_type(target_class)
        names = src_desc.get_property_names()

        for prop in names:
            if prop in self.exceptions:
                continue
            if src_desc.has_property(prop) and tgt_desc.has_property(prop):
                result.append(prop)
        return result

def properties(properties_list: List[str]) -> Properties:
    return Properties(properties_list)

def matching_properties() -> AllProperties:
    return AllProperties()

@dataclass
class Match:
    operation: MapOperation
    source: List[Accessor]
    target: List[Accessor]
    paths: List[List[Accessor]] = None
    def __post_init__(self):
        self.paths = [self.source, self.target]

class MapProperties(MapOperation):
    def __init__(self, qualifier: PropertyQualifier, converter: Optional[Convert]=None, deep: bool=False):
        super().__init__(converter=converter, deep=deep)
        self.qualifier = qualifier
    def compute_properties(self, source_class: Type, target_class: Type) -> List[str]:
        return self.qualifier.compute_properties(source_class, target_class)
    def find_matches(self, definition, matches: List[Match]):
        for prop in self.compute_properties(definition.source_class, definition.target_class):
            matches.append(Match(operation=self, source=[PropertyAccessor(name=prop)], target=[PropertyAccessor(name=prop)]))

class MapAccessor(MapOperation):
    def __init__(self, source: List[Accessor], target: List[Accessor], converter: Optional[Convert]=None, deep: bool=False):
        super().__init__(converter=converter, deep=deep)
        self.source = source
        self.target = target
    def find_matches(self, definition, matches: List[Match]):
        matches.append(Match(operation=self, source=self.source, target=self.target))

# MappingDefinition, Mapping, MappingContext, Mapper

def path(*args: str):
    return [x for x in args if x is not None]

class MappingDefinition(Generic[S, T]):
    def __init__(self, source: Type[S] = None, target: Type[T] = None):
        self.source_class: Type[S] = source
        self.target_class: Type[T] = target
        self.operations: List[MapOperation] = []
        self.intermediate_result_definitions = []
        self.finalizer = None
        self.base_mapping = None

    def add_intermediate_result_definition(self, type_descriptor, constructor, nargs, value_receiver):
        ir = IntermediateResultDefinition(type_descriptor=type_descriptor, constructor=constructor, index=len(self.intermediate_result_definitions), n_args=nargs, value_receiver=value_receiver)
        self.intermediate_result_definitions.append(ir)
        return ir

    def collect_finalizer(self):
        finalizers = []
        def collect(defn):
            if defn.base_mapping is not None:
                collect(defn.base_mapping)
            if defn.finalizer is not None:
                finalizers.append(defn.finalizer)
        collect(self)
        return finalizers

    def find_matches(self, matches: List[Match]):
        if self.base_mapping is not None:
            self.base_mapping.find_matches(matches)
        for op in self.operations:
            op.find_matches(self, matches)

    def create_operations(self, mapper):
        matches = []
        self.find_matches(matches)

        return OperationBuilder(matches).make_operations(mapper, self)

    def create_mapping(self, mapper):
        result = self.create_operations(mapper)
        for intermediate in self.intermediate_result_definitions:
            if intermediate.missing > 0:
                raise MapperException(f"{intermediate.type_descriptor.type} misses {intermediate.missing} arguments")
        mapping = Mapping(mapper=mapper,
                          definition=self,
                          constructor=result.constructor,
                          stack_size=result.stack_size,
                          intermediate_result_definitions=self.intermediate_result_definitions,
                          operations=result.operations,
                          finalizer=self.collect_finalizer())
        return mapping

    def map(self, constant=None, from_=None, all=None, to=None, deep=False, validate=False, convert: Optional[Convert]=None):
        if all is not None:
            self.operations.append(MapProperties(qualifier=all, converter=convert, deep=deep))
        else:
            from_accessors = []
            to_accessors = []
            if isinstance(from_, Accessor):
                from_accessors.append(from_)
            elif isinstance(from_, str):
                from_accessors.append(PropertyAccessor(name=from_))
            elif isinstance(from_, list):
                from_accessors = [PropertyAccessor(name=s) for s in from_]
            if constant is not None:
                from_accessors.append(ConstantAccessor(value=constant))
            if isinstance(to, Accessor):
                to_accessors.append(to)
            elif isinstance(to, str):
                to_accessors.append(PropertyAccessor(name=to, validate=validate))
            elif isinstance(to, list):
                to_accessors = [PropertyAccessor(name=s, validate=validate) for s in to]
            self.operations.append(MapAccessor(source=from_accessors, target=to_accessors, converter=convert, deep=deep))
        return self

    def finalize(self, finalizer_func: Callable):
        self.finalizer = finalizer_func
        return self

def mapping(source: Type[S] = None, target: Type[T] = None) -> MappingDefinition[S, T]:
    return MappingDefinition(source=source, target=target)

class MappingState:
    def __init__(self, context):
        self.context = context
        self.result_buffers = context.result_buffers
        self.stack = context.stack
        self.result = None
        self.next_state = context.current_state
        context.current_state = self
    def restore(self, context):
        context.result_buffers = self.result_buffers
        context.stack = self.stack
        context.current_state = self.next_state

class MappingContext:
    def __init__(self, mapper):
        self.mapper = mapper
        self.current_source = None
        self.current_target = None
        self.mapped_objects = None
        self.result_buffers = []
        self.stack = []
        self.current_state = None
        if getattr(mapper, 'check_cycles', False):
            self.mapped_objects = {}
    def remember(self, source, target):
        if self.mapped_objects is not None:
            self.mapped_objects[id(source)] = target
        self.current_source = source
        self.current_target = target
        return self
    def mapped_object(self, source):
        return None if self.mapped_objects is None else self.mapped_objects.get(id(source))
    def setup_result_buffers(self, buffers):
        saved = self.result_buffers
        self.result_buffers = buffers
        return saved
    def setup(self, intermediate_result_definitions, stack_size: int):
        buffers = [ir.create_buffer() for ir in intermediate_result_definitions]
        if stack_size > 0:
            self.stack = [None] * stack_size
        return self.setup_result_buffers(buffers)
    def get_result_buffer(self, index: int):
        return self.result_buffers[index]
    def push(self, value, index: int):
        self.stack[index] = value
    def peek(self, index: int):
        return self.stack[index]

class MappingKey:
    def __init__(self, source: Type, target: Type):
        self.source = source
        self.target = target
    def _type_matches(self, a: Type, b: Type) -> bool:
        return a == b or a == object or b == object
    def __eq__(self, other):
        if not isinstance(other, MappingKey):
            return False
        return self._type_matches(self.source, other.source) and self._type_matches(self.target, other.target)
    def __hash__(self):
        return 0

class Mapping(Generic[S, T], Transformer[MappingContext]):
    def __init__(self, mapper, definition: MappingDefinition[S, T], constructor, stack_size, intermediate_result_definitions, operations, finalizer):
        super().__init__(operations=operations)

        self.mapper = mapper
        self.definition = definition
        self.constructor = constructor
        self.stack_size = stack_size
        self.intermediate_result_definitions = intermediate_result_definitions
        self.finalizer = finalizer or []
        self.type_descriptor = TypeDescriptor.for_type(definition.target_class)
        self.lazy = self.type_descriptor.is_immutable() or not self.type_descriptor.has_default_constructor()
    def setup_context(self, context: MappingContext):
        state = MappingState(context)
        context.setup(self.intermediate_result_definitions, self.stack_size)
        return state

    def new_instance(self) -> T:
        return self.constructor()

    def transform_target(self, source: S, target: T, context: MappingContext):
        for op in self.operations:
            op.set_target(source, target, context)


class Mapper(Generic[S, T]):

    def __init__(self, *definitions: MappingDefinition, config: Optional[dict]=None):
        self.mapping_definitions = list(definitions)
        self.mappings: Dict[MappingKey, Mapping[Any, Any]] = {}
        self.by_source_type_mappings: Dict[Type, Mapping[Any, Any]] = {}
        self.check_cycles = False
        for definition in definitions:
            mapping = definition.create_mapping(self)
            self.register_mapping(mapping)
        if config is not None:
            self.check_cycles = config.get('check_cycles', False)
    def create_context(self):
        return MappingContext(self)
    def register_mapping(self, mapping: Mapping):
        key = MappingKey(mapping.definition.source_class, mapping.definition.target_class)
        self.mappings[key] = mapping
    def has_definition(self, source: Type, target: Type) -> bool:
        for d in self.mapping_definitions:
            if d.source_class == source and d.target_class == target:
                return True
        return False
    def get_source_mapping(self, source: Type):
        m = self.by_source_type_mappings.get(source)
        if m is None:
            for mapping in self.mappings.values():
                if mapping.definition.source_class == source:
                    self.by_source_type_mappings[source] = mapping
                    return mapping
            raise MapperException(f"no mapping for source type {source}")
        return m
    def get_mapping_x(self, source: Type, target: Type):
        key = MappingKey(source, target)
        m = self.mappings.get(key)
        if m is None:
            raise MapperException(f"No mapping found for <{source}, {target}>")
        return m

    def map(self, source: S, target: Optional[T] = None, context: Optional[MappingContext]=None, mapping: Optional[Mapping[S, T]]=None) -> Optional[T]:
        if source is None:
            return None
        # if mapping not provided, try to infer by source runtime type and a registered mapping
        mapping = mapping or self.get_source_mapping(type(source))
        context = context or MappingContext(self)
        if target is None:
            target = context.mapped_object(source)
        lazy_create = False
        if target is None:
            lazy_create = mapping.lazy
            if lazy_create:
                target = context
            else:
                target = mapping.new_instance()
                context.remember(source, target)

        state = mapping.setup_context(context)
        try:
            mapping.transform_target(source, target, context)
            if lazy_create:
                target = context.current_state.result
                context.remember(source, target)
        finally:
            state.restore(context)

        for finalizer in mapping.finalizer:
            finalizer(source, target)

        return target
