"""
This module provides the core Aspyx service management framework allowing for service discovery and transparent remoting including multiple possible transport protocols.
"""

from aspyx.di import module

from .service import AuthorizationException, MissingTokenException, RemoteServiceException, ServiceCommunicationException, TokenException, TokenExpiredException, InvalidTokenException, component_services, ServiceException, Server, Channel, ComponentDescriptor, inject_service, ChannelAddress, ChannelInstances, ServiceManager, Component, Service, AbstractComponent, ComponentStatus, ComponentRegistry, implementation, health, component, service
from .channels import HTTPXChannel, DispatchJSONChannel
from .registries import ConsulComponentRegistry
from .server import FastAPIServer, RequestContext
from .healthcheck import health_checks, health_check, HealthCheckManager, HealthStatus
from .restchannel import RestChannel, post, get, put, delete, QueryParam, Body, rest
from .session import Session, SessionManager
from .authorization import AuthorizationManager, AbstractAuthorizationFactory, AuthorizationException


@module()
class ServiceModule:
    def __init__(self):
        pass

__all__ = [
    # service

    "ServiceManager",
    "ServiceModule",
    "ServiceException",
    "Server",
    "Component",
    "Service",
    "Channel",
    "AbstractComponent",
    "ComponentStatus",
    "ComponentDescriptor",
    "ComponentRegistry",
    "ChannelAddress",
    "ChannelInstances",
    "health",
    "component",
    "service",
    "implementation",
    "inject_service",
    "component_services",
    "RemoteServiceException",
    "ServiceCommunicationException",
    "TokenException",
    "TokenExpiredException",
    "InvalidTokenException",
    "MissingTokenException",
    "AuthorizationException",

    # authorization

    "AuthorizationManager",
    "AbstractAuthorizationFactory",
    "AuthorizationException",

    # session

    "Session",
    "SessionManager",

    # healthcheck

    "health_checks",
    "health_check",
    "HealthStatus",
    "HealthCheckManager",

    # serialization

   # "deserialize",

    # channel

    "HTTPXChannel",
    "DispatchJSONChannel",

    # rest

    "RestChannel",
    "post",
    "get",
    "put",
    "delete",
    "rest",
    "QueryParam",
    "Body",

    # registries

    "ConsulComponentRegistry",
    "RequestContext",

    # server

    "FastAPIServer",
    "RequestContext"
]
