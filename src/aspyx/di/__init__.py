"""
This module provides dependency injection and aop capabilities for Python applications.
"""
from .di import DIException, AbstractCallableProcessor, LifecycleCallable, Lifecycle, Providers, Environment, ClassInstanceProvider, injectable, factory, environment, inject, order, create, on_init, on_running, on_destroy, inject_environment, Factory, PostProcessor

# import something from the subpackages, so that teh decorators are executed

from .configuration import ConfigurationManager
from .aop import before

imports = [ConfigurationManager, before]

__all__ = [
    "ClassInstanceProvider",
    "Providers",
    "Environment",
    "injectable",
    "factory",
    "environment",
    "inject",
    "create",
    "order",

    "on_init",
    "on_running",
    "on_destroy",
    "inject_environment",
    "Factory",
    "PostProcessor",
    "AbstractCallableProcessor",
    "LifecycleCallable",
    "DIException",
    "Lifecycle"
]
