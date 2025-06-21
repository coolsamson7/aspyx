"""
This module provides dependency injection and aop capabilities for Python applications.
"""
from .di import InstanceProvider, conditional, requires_class, requires_feature, DIException, AbstractCallableProcessor, LifecycleCallable, Lifecycle, Providers, Environment, ClassInstanceProvider, injectable, factory, module, inject, order, create, on_init, on_running, on_destroy, inject_environment, Factory, PostProcessor

# import something from the subpackages, so that the decorators are executed

from .configuration import ConfigurationManager
from .aop import before
from .threading import SynchronizeAdvice

imports = [ConfigurationManager, before, SynchronizeAdvice]

__all__ = [
    "ClassInstanceProvider",
    "Providers",
    "Environment",
    "injectable",
    "factory",
    "module",
    "inject",
    "create",
    "order",
    "InstanceProvider",
    "on_init",
    "on_running",
    "on_destroy",
    "inject_environment",
    "Factory",
    "PostProcessor",
    "AbstractCallableProcessor",
    "LifecycleCallable",
    "DIException",
    "Lifecycle",
    "conditional",
    "requires_class",
    "requires_feature"
]
