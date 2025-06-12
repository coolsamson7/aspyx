"""
This module provides dependency injection and aop capabilities for Python applications.
"""
from .di import InjectorException, CallableProcessor, LifecycleCallable, Lifecycle, Providers, Environment, ClassInstanceProvider, injectable, factory, environment, inject, create, on_init, on_destroy, inject_environment, Factory, PostProcessor

# import something from the subpackages, so that teh decorators are executed

from aspyx.di.configuration import ConfigurationManager
from aspyx.di.aop import before

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

    "on_init",
    "on_destroy",
    "inject_environment",
    "Factory",
    "PostProcessor",
    "CallableProcessor",
    "LifecycleCallable",
    "InjectorException",
    "Lifecycle"
]
