"""
Sub module
"""
from aspyx.di import module, injectable

@module()
class SubImportModule:
    pass

@injectable()
class Sub:
    pass
