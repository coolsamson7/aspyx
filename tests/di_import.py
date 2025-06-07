from aspyx.di import configuration, injectable

@configuration()
class ImportConfiguration:
    def __init__(self):
        pass

@injectable()
class ImportedClass:
    def __init__(self):
        pass