from aspyx.di import order, inject
from aspyx.reflection import Decorators
from .authorization_manager import AuthorizationManager

class AbstractAuthorizationFactory(AuthorizationManager.AuthorizationFactory):
    """
    Abstract base class for authorization factories
    """

    # constructor

    def __init__(self):
        super().__init__(0)

        if Decorators.has_decorator(type(self), order):
            self.order = Decorators.get_decorator(type(self), order).args[0]

    # inject

    @inject()
    def set_authorization_manager(self, authorization_manager: AuthorizationManager):
        authorization_manager.register_factory(self)
