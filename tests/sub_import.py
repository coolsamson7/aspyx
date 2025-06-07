from aspyx.di import configuration, injectable

@configuration()
class SubImportConfiguration:
    def __init__(self):
        pass

@injectable()
class Sub:
    def __init__(self):
        pass