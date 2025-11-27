from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Callable, Dict, List, Any, Optional

S = TypeVar("S")   # Source type (DTO)
T = TypeVar("T")   # Target type (Entity)
PK = TypeVar("PK") # Primary key type


class RelationSynchronizer(ABC, Generic[S, T, PK]):
    """
    Generic synchronizer for 1:N or N:M relationships.
    Automatically matches entities by primary key, updates, adds, and deletes as needed.
    """

    def __init__(self, to_pk: Callable[[S], PK], pk: Callable[[T], PK]):
        self.to_pk = to_pk   # function to extract PK from source
        self.pk = pk         # function to extract PK from target

    # --- protected hooks ------------------------------------------------------

    def missing_pk(self, key: PK) -> bool:
        """Override if certain PK values should be ignored (e.g., None)."""
        return key is None

    @abstractmethod
    def provide(self, source: S, context: Any) -> T:
        """Create a new target entity for a given source DTO."""
        raise NotImplementedError

    def delete(self, entity: T):
        """Called for deleted target entities."""
        pass

    def update(self, target: T, source: S, context: Any):
        """Called when a target already exists and needs updating."""
        pass

    def add_to_relation(self, relation: List[T], target: T):
        """Default behavior for adding to a collection."""
        relation.append(target)

    def remove_from_relation(self, relation: List[T], target: T):
        """Default behavior for removing from a collection."""
        relation.remove(target)

    # --- main logic -----------------------------------------------------------

    def synchronize(self, source: List[S], target: List[T], context: Any):
        """
        Synchronize target collection with source collection.

        - Adds new entities for new sources.
        - Updates existing entities with matching PKs.
        - Removes and deletes entities missing from source.
        """
        target_map: Dict[PK, T] = {}

        # Build PK -> Entity map for fast lookup
        for t in target:
            key = self.pk(t)
            if key is not None:
                target_map[key] = t

        # Iterate source DTOs
        for s in source:
            key = self.to_pk(s)
            if not self.missing_pk(key):
                t = target_map.pop(key, None)

                if t is None:
                    # New entity
                    self.add_to_relation(target, self.provide(s, context))
                else:
                    # Update existing
                    self.update(t, s, context)
            else:
                # Missing PK: treat as new
                self.add_to_relation(target, self.provide(s, context))

        # Anything left in target_map is deleted
        for deleted in target_map.values():
            self.remove_from_relation(target, deleted)
            self.delete(deleted)
