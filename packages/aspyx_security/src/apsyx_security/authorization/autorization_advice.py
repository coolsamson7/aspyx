from aspyx.di import injectable
from aspyx.di.aop import advice, Invocation, methods, classes, around

from .authorization_manager import AuthorizationManager
from ..session import SessionManager
from .auhorization_exception import AuthorizationException

from .secure import secure

from ..session import SessionContext

@advice
@injectable()
class AuthorizationAdvice:
    """
    This advice adds the appropriate aspects for services annotated with `@secure`
    """
    # constructor

    def __init__(self, authorization_manager: AuthorizationManager, session_manager: SessionManager):
        self.authorization_manager = authorization_manager

        #session_manager.set_factory(lambda token: UserSession(user=token.get("sub"), roles=token.get("roles")))

    # internal

    def authorize(self, invocation: Invocation):
        #try:
            self.authorization_manager.authorize(invocation)
        #except AuthorizationException as e:
            #ServiceManager.logger.warning(f"Authorization failed ({invocation.func.__name__}): {str(e)}")

        #    raise HTTPException(status_code=403, detail=str(e) + f" in function {invocation.func.__name__}")

    # aspects

    @around(methods().that_are_async().decorated_with(secure),
            methods().that_are_async().declared_by(classes().decorated_with(secure)))
    async def authorize_async(self, invocation: Invocation):
        try:
            self.authorize(invocation)

            return await invocation.proceed_async()
        finally:
            SessionContext.clear()
            #TokenContext.clear()

    @around(methods().that_are_sync().decorated_with(secure),
            methods().that_are_sync().declared_by(classes().decorated_with(secure)))
    def authorize_sync(self, invocation: Invocation):
        try:
            self.authorize(invocation)

            return invocation.proceed()
        finally:
            SessionContext.clear()
            #TokenContext.clear()