"""
Logging utility class
"""
import logging
import sys
from typing import Optional, Dict

class Logger:
    """just syntactic sugar"""

    @classmethod
    def configure(cls,
                 default_level: int = logging.INFO,
                 format: str = "[%(asctime)s] %(levelname)s in %(filename)s:%(lineno)d - %(message)s",
                 levels: Optional[Dict[str, int]] = None, stream=sys.stdout):
        logging.basicConfig(level=default_level, format=format)
        if levels is not None:
            for name, level in levels.items():
                logging.getLogger(name).setLevel(level)
