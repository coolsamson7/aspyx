"""
YamlConfigurationSource - Loads variables from a YAML configuration file.
"""
import yaml

from .configuration import ConfigurationSource

class YamlConfigurationSource(ConfigurationSource):
    """
    YamlConfigurationSource loads variables from a YAML configuration file.
    """

    __slots__ = ["file"]

    # constructor

    def __init__(self, file: str):
        super().__init__()

        self.file = file

    # implement

    def load(self) -> dict:
        with open(self.file, "r") as file:
            return yaml.safe_load(file)
