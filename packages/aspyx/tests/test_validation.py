import unittest

from pydantic import BaseModel, Field
from pydantic.dataclasses import dataclass

from aspyx.reflection import TypeDescriptor
from aspyx.reflection.reflection import attribute
from aspyx.validation.validation import IntType, StringType, ValidationException, string


@dataclass
class DataClass:
    id : str = attribute(primary_key=True, type_property=string().max_length(10))

class PydanticClass(BaseModel):
    id: str = Field(json_schema_extra={"primary_key": True, "type_property": string().max_length(10)})

class TestValidation(unittest.TestCase):
    def test_constraints(self):
        type = IntType().min(5).max(10)

        self.assertTrue(type.is_valid(7))
        self.assertFalse(type.is_valid(3))


        type = StringType().not_empty().min_length(3)
        try:
            type.validate("hi")
            self.fail("should fail")
        except ValidationException as e:
            print("Validation failed:\n", e)

    def test_typedescriptor(self):
        data_class_descriptor = TypeDescriptor.for_type(DataClass)
        pydantic_class_descriptor =  TypeDescriptor.for_type(PydanticClass)

        self.assertTrue(True)