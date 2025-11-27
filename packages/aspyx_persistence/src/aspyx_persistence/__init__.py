"""
This module provides the core Aspyx event management framework .
"""
from aspyx.di import module

from typing import Type

from sqlalchemy.orm import ColumnProperty, class_mapper, RelationshipProperty

from aspyx.reflection import TypeDescriptor
from aspyx.reflection.reflection import PropertyExtractor
from .transactional import transactional, transaction, get_current_session
from .repository import BaseRepository, query
from .relation_synchronizer import RelationSynchronizer
from .persistent_unit import PersistentUnit

class SQLAlchemyPropertyExtractor(PropertyExtractor):
    def extract(self, cls: Type):
        try:
            mapper = class_mapper(cls)
        except Exception:
            return None

        props = {}

        for prop in mapper.iterate_properties:
            # -------------------------------
            # Handle Columns
            # -------------------------------
            if isinstance(prop, ColumnProperty):
                column = prop.columns[0]

                # Skip foreign key columns (technical)
                if column.foreign_keys:
                    continue

                info = getattr(column, "info", {}) or {}
                typ = getattr(column.type, "python_type", object)
                default = getattr(column, "default", None)

                p = TypeDescriptor.PropertyDescriptor(cls, prop.key, typ, default)
                p.primary_key = column.primary_key
                p.type_property = info.get("type_property", None)
                props[prop.key] = p

            # -------------------------------
            # Handle Relationships
            # -------------------------------
            elif isinstance(prop, RelationshipProperty):
                related_class = prop.mapper.class_

                if prop.uselist:
                    from typing import List
                    typ = List[related_class]
                else:
                    typ = related_class

                p = TypeDescriptor.PropertyDescriptor(
                    cls,
                    prop.key,
                    typ,
                    None
                )
                p.is_relationship = True
                p.uselist = prop.uselist
                p.direction = str(prop.direction)
                p.back_populates = getattr(prop, "back_populates", None)
                props[prop.key] = p

        return props

TypeDescriptor.register_extractor(SQLAlchemyPropertyExtractor())

@module()
class PersistenceModule:
    def __init__(self):
        pass


__all__ = [
    #

    "PersistenceModule",

    # persistent_unit

    # repository

    "BaseRepository",
    "query",

    # transactional

    "transactional",
    "transaction",
    "get_current_session",

    # relation_synchronizer

    "RelationSynchronizer"
]

