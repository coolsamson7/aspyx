"""
This module provides the core Aspyx service management framework allowing for service discovery and transparent remoting including multiple possible transport protocols.
"""

from aspyx.di import module

from .service import AuthorizationException, MissingTokenException, RemoteServiceException, ServiceCommunicationException, TokenException, TokenExpiredException, InvalidTokenException, component_services, ServiceException, Server, Channel, ComponentDescriptor, inject_service, ChannelAddress, ChannelInstances, ServiceManager, Component, Service, AbstractComponent, ComponentStatus, ComponentRegistry, implementation, health, component, service
from .channels import HTTPXChannel, DispatchJSONChannel, TokenContext
from .registries import ConsulComponentRegistry
from .server import FastAPIServer, RequestContext, ResponseContext, TokenContextMiddleware
from .healthcheck import health_checks, health_check, HealthCheckManager, HealthStatus
from .restchannel import RestChannel, post, get, put, delete, QueryParam, PathParam, Body, rest
from .session import Session, SessionManager, SessionContext
from .authorization import AuthorizationManager, AbstractAuthorizationFactory
from .protobuf import ProtobufManager

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

    # protobuf

    "ProtobufManager",

    # authorization

    "AuthorizationManager",
    "AbstractAuthorizationFactory",

    # session

    "Session",
    "SessionManager",
    "SessionContext",

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
    "TokenContext",

    # rest

    "RestChannel",
    "post",
    "get",
    "put",
    "delete",
    "rest",
    "QueryParam",
    "PathParam",
    "Body",

    # registries

    "ConsulComponentRegistry",

    # server

    "FastAPIServer",
    "RequestContext",
    "ResponseContext",
    "TokenContext",
    "TokenContextMiddleware",
]
