"""
This module provides the core Aspyx service management framework allowing for service discovery and transparent remoting including multiple possible transport protocols.
"""

from aspyx.di import module

from .service import ServiceException, Server, Channel, ComponentDescriptor, inject_service, ChannelAddress, ChannelInstances, ServiceManager, Component, Service, AbstractComponent, ComponentStatus, ComponentRegistry, implementation, health, component, service
from .channels import HTTPXChannel, DispatchJSONChannel, remember_token, clear_token
from .registries import ConsulComponentRegistry
from .server import FastAPIServer, RequestContext
from .healthcheck import health_checks, health_check, HealthCheckManager, HealthStatus
from .restchannel import RestChannel, post, get, put, delete, QueryParam, Body, rest


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
    "remember_token",
    "clear_token"

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

    "FastAPIServer"
]
