"""
EnvConfigurationSource - Loads environment variables as configuration source.
"""
import os

from dotenv import load_dotenv

from .configuration import ConfigurationSource

class EnvConfigurationSource(ConfigurationSource):
    """
    EnvConfigurationSource loads all environment variables.
    """

    __slots__ = []

    # constructor

    def __init__(self):
        super().__init__()

    # implement

    def load(self) -> dict:
        def merge_dicts(a, b):
            """Recursively merges b into a"""
            for key, value in b.items():
                if isinstance(value, dict) and key in a and isinstance(a[key], dict):
                    merge_dicts(a[key], value)
                else:
                    a[key] = value
            return a

        def explode_key(key, value):
            """Explodes keys with '.' or '/' into nested dictionaries"""
            parts = key.replace('/', '.').split('.')
            d = current = {}
            for part in parts[:-1]:
                current[part] = {}
                current = current[part]
            current[parts[-1]] = value
            return d

        exploded = {}

        load_dotenv()

        for key, value in os.environ.items():
            if '.' in key or '/' in key:
                partial = explode_key(key, value)
                merge_dicts(exploded, partial)
            else:
                exploded[key] = value

        return exploded
