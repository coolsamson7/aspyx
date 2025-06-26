"""
Import
"""
from aspyx.di import module, injectable

@module()
class ImportedModule:
    def __init__(self):
        pass

@injectable()
class ImportedClass:
    def __init__(self):
        pass
