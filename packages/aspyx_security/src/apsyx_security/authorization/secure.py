from aspyx.reflection import Decorators


def secure():
    """
    services decorated with `@secure` will add an authentication / authorization aspect
    """
    def decorator(cls):
        Decorators.add(cls, secure)

        return cls

    return decorator