"""
Sub module
"""
from aspyx.di import environment, injectable

@environment()
class SubImportConfiguration:
    def __init__(self):
        pass

@injectable()
class Sub:
    def __init__(self):
        pass
