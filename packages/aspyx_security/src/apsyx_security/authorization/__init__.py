"""
This module provides the core Aspyx security management framework .
"""
from aspyx.di import module

from .authorization_manager import AuthorizationManager
from .abstract_authorization_factory import AbstractAuthorizationFactory
from .secure import secure
from .auhorization_exception import AuthorizationException

@module()
class SecurityModule:
    def __init__(self):
        pass

__all__ = [
    # package

    "SecurityModule",

    # authorization_manager

    "AuthorizationManager",

    # abstract_authorization_factory

    "AbstractAuthorizationFactory",

    # secure

    "secure",

    # auhorization_exception

    "AuthorizationException"
]
