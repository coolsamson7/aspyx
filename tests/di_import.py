"""
Import
"""
from aspyx.di import environment, injectable

@environment()
class ImportedEnvironment:
    def __init__(self):
        pass

@injectable()
class ImportedClass:
    def __init__(self):
        pass
