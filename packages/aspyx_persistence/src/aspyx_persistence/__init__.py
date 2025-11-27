"""
This module provides the core Aspyx event management framework .
"""
from aspyx.di import module

@module()
class PersistenceModule:
    def __init__(self):
        pass

__all__ = [
    # package

    "PersistenceModule",
]
