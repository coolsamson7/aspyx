"""
Import
"""
from aspyx.di import module, injectable

@module()
class ImportedModule:
    pass

@injectable()
class ImportedClass:
    pass
