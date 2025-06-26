"""
Sub module
"""
from aspyx.di import module, injectable

@module()
class SubImportModule:
    def __init__(self):
        pass

@injectable()
class Sub:
    def __init__(self):
        pass
