"""
registries for components in aspyx service
"""
import re
import threading
from abc import abstractmethod
import time
from typing import Optional
from urllib.parse import urlparse

import consul

from aspyx.util import StringBuilder
from aspyx.di import on_init
from .healthcheck import HealthCheckManager, HealthStatus

from .server import Server
from .service import ComponentRegistry, Channel, ChannelInstances, ServiceManager, ComponentDescriptor, Component, ChannelAddress

class ConsulComponentRegistry(ComponentRegistry):
    """
    A specialized registry using consul.
    A polling mechanism is used to identify changes in the component health.
    """
    # constructor

    def __init__(self, port: int, consul_url: str):
        self.port = port
        self.ip = Server.get_local_ip()
        self.running = False
        self.consul = None
        self.watchdog = None
        self.interval = 5
        self.last_index = {}
        self.component_addresses : dict[str, dict[str, ChannelInstances]] = {} # comp -> channel -> address
        self.watch_channels : list[Channel] = []

        parsed = urlparse(consul_url)

        self.consul_host = parsed.hostname
        self.consul_port = parsed.port

    def make_consul(self, host="", port="") -> consul.Consul:
        """
        create and return a consul instance

        Args:
            host: the host
            port: the port

        Returns:
            a consul instance

        """
        return consul.Consul(host=host, port=port)

    # lifecycle hooks

    @on_init()
    def setup(self):
        # create consul client

        self.consul = self.make_consul(host=self.consul_host, port=self.consul_port)
        self.running = True

        # start thread

        self.watchdog = threading.Thread(target=self.watch_consul, daemon=True)
        self.watchdog.start()

    def inform_channels(self, old_address: ChannelInstances, new_address: Optional[ChannelInstances]):
        for channel in self.watch_channels:
            if channel.address is old_address:
                channel.set_address(new_address)


    def watch_consul(self):
        while self.running:
            # check services

            for component, old_addresses in self.component_addresses.items():
                old_addresses = dict(old_addresses) # we will modify it...
                new_addresses = self.fetch_addresses(component, wait="1s")

                # compare

                changed = False
                for channel_name, address in new_addresses.items():
                    service_address = old_addresses.get(channel_name, None)
                    if service_address is None:
                        ServiceManager.logger.info("new %s address for %s", channel_name, component)
                        changed = True
                    else:
                        if service_address != address:
                            changed = True

                            ServiceManager.logger.info("%s address for %s changed", channel_name, component)

                            # inform channels

                            self.inform_channels(service_address, address)

                        # delete

                        del old_addresses[channel_name]

                # watchout for deleted addresses

                for channel_name, address in old_addresses.items():
                    ServiceManager.logger.info("deleted %s address for %s", channel_name, component)

                    changed = True

                    # inform channel

                    self.inform_channels(address, None)

                # replace ( does that work while iterating )

                if changed:
                    self.component_addresses[component] = new_addresses

            # time to sleep

            time.sleep(5)

    @abstractmethod
    def watch(self, channel: Channel) -> None:
        self.watch_channels.append(channel)

        #self.component_addresses[channel.component_descriptor.name] = {}

   # public

    def register_service(self, name, service_id, health: str, tags=None, meta=None) -> None:
        self.consul.agent.service.register(
            name=name,
            service_id=service_id,
            address=self.ip,
            port=self.port,
            tags=tags or [],
            meta=meta or {},
            check=consul.Check().http(
                url=f"http://{self.ip}:{self.port}{health}",
                interval="10s",
                timeout="3s",
                deregister="5m")
            )

    def deregister(self, descriptor: ComponentDescriptor[Component]) -> None:
        name = descriptor.name

        service_id = f"{self.ip}:{self.port}:{name}"

        self.consul.agent.service.deregister(service_id)

    def stop(self):
        self.running = False
        if self.watchdog is not None:
            self.watchdog.join()
            self.watchdog = None

    # private

    def fetch_addresses(self, component: str, wait=None) -> dict[str, ChannelInstances]:
        addresses : dict[str, ChannelInstances] = {} # channel name -> ServiceAddress

        index, nodes = self.consul.health.service(component, passing=True, index=self.last_index.get(component, None), wait=wait)
        self.last_index[component] = index

        for node in nodes:
            service = node["Service"]

            meta = service.get('Meta')

            channels = meta.get("channels").split(",")

            for channel in channels:
                match = re.search(r"([\w-]+)\((.*)\)", channel)

                channel_name = match.group(1)
                url = match.group(2)

                address = addresses.get(channel, None)
                if address is None:
                    address = ChannelInstances(component=component, channel=channel_name)
                    addresses[channel] = address

                address.urls.append(url)

        # done

        return addresses

    # implement ComponentRegistry

    def register(self, descriptor: ComponentDescriptor[Component], addresses: list[ChannelAddress]):
        name = descriptor.name

        id = f"{self.ip}:{self.port}:{name}"

        builder = StringBuilder()
        first = True
        for address in addresses:
            if not first:
                builder.append(",")

            builder.append(address.channel).append("(").append(address.uri).append(")")

            first = False

        addresses = str(builder)

        self.register_service(name, id, descriptor.health, tags =["component"], meta={"channels": addresses})

    def get_addresses(self, descriptor: ComponentDescriptor) -> list[ChannelInstances]:
        component_addresses = self.component_addresses.get(descriptor.name, None)
        if component_addresses is None:
            component_addresses = self.fetch_addresses(descriptor.name)

            # only cache if non-empty

            if len(component_addresses) > 0:
                self.component_addresses[descriptor.name] = component_addresses

        return list(component_addresses.values())

    #200–299	passing	Service is healthy (OK, Created, No Content…)
    #429	warning	Rate limited or degraded
    #300–399	warning	Redirects interpreted as potential issues
    #400–499	critical	Client errors (Bad Request, Unauthorized…)
    #500–599	critical	Server errors (Internal Error, Timeout…)
    #Other / No response	critical	Timeout, connection refused, etc.
    def map_health(self, health: HealthCheckManager.Health) -> int:
        if health.status is HealthStatus.OK:
            return 200
        elif health.status is HealthStatus.WARNING:
            return 429
        else:
            return 500
