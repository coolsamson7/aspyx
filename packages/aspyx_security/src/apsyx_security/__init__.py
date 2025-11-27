"""
This module provides the core Aspyx security management framework .
"""
from aspyx.di import module

@module()
class SecurityModule:
    def __init__(self):
        pass

__all__ = [
    # package

    "SecurityModule"
]
