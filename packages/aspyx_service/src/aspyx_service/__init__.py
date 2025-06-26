"""
This module provides the core Aspyx service management framework allowing for service discovery and transparent remoting including multiple possible transport protocols.
"""

from aspyx.di import module

from .service import ServiceException, Server, Channel, ComponentDescriptor, inject_service, ChannelAddress, ServiceAddress, ServiceManager, Component, Service, AbstractComponent, ComponentStatus, ComponentHealth, ComponentRegistry, implementation, health, component, service
from .channels import HTTPXChannel, DispatchJSONChannel
from .registries import ConsulComponentRegistry
from .server import FastAPIServer


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
    "ComponentHealth",
    "ComponentRegistry",
    "ChannelAddress",
    "ServiceAddress",
    "health",
    "component",
    "service",
    "implementation",
    "inject_service",

    # serialization

   # "deserialize",

    # channel

    "HTTPXChannel",
    "DispatchJSONChannel",

    # registries

    "ConsulComponentRegistry",

    # server

    "FastAPIServer"
]
