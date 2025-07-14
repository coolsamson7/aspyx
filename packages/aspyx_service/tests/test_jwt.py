"""
jwt sample test
"""
import faulthandler
import time
from typing import Optional

from aspyx.di.configuration import inject_value
from aspyx.util import Logger

faulthandler.enable()

import logging
from abc import abstractmethod

from fastapi import Request as HttpRequest, HTTPException

from datetime import datetime, timezone

Logger.configure(default_level=logging.DEBUG, levels={
    "httpx": logging.ERROR,
    "aspyx.di": logging.ERROR,
    "aspyx.di.aop": logging.ERROR,
    "aspyx.service": logging.ERROR,
    "aspyx.event": logging.DEBUG
})

from aspyx_service import Service, service, component, implementation, AbstractComponent, \
    Component, ChannelAddress, Server, health, RequestContext, HTTPXChannel, \
    AbstractAuthorizationFactory, AuthorizationManager, SessionManager, AuthorizationException, Session, \
    ServiceCommunicationException, TokenExpiredException, ServiceManager, TokenContext, SessionContext

from aspyx.reflection import Decorators, TypeDescriptor

from aspyx.di import injectable, order
from aspyx.di.aop import advice, around, Invocation, methods, classes


from .common import service_manager, TokenManager

# decorator

def secure():
    """
    services decorated with `@secure` will add an authentication / authorization aspect
    """
    def decorator(cls):
        Decorators.add(cls, secure)

        return cls

    return decorator

# session

class UserSession(Session):
    """
    A simple session class covering th user and roles.
    """
    # constructor

    def __init__(self, user: str, roles: list[str]):
        super().__init__()

        self.user = user
        self.roles = roles

# advice

def requires_role(role=""):
    """
    Methods decorated with `@requires_role` will only be allowed if the current user has the given role.
    """
    def decorator(func):
        Decorators.add(func, requires_role, role)

        return func

    return decorator


@injectable()
@order(1)
class RoleAuthorizationFactory(AbstractAuthorizationFactory):
    """
    An `AuthorizationFactory` that will look for `@requires_role` and will add the appropriate check
    """
    # local class

    class RoleAuthorization(AuthorizationManager.Authorization):
        # constructor

        def __init__(self, role: str):
            self.role = role

        # implement

        def authorize(self, invocation: Invocation):
            if not self.role in SessionContext.get(UserSession).roles:
                raise AuthorizationException(f"expected role {self.role}")

    # implement

    def compute_authorization(self, method_descriptor: TypeDescriptor.MethodDescriptor) -> Optional[AuthorizationManager.Authorization]:
        if method_descriptor.has_decorator(requires_role):
            role = method_descriptor.get_decorator(requires_role).args[0]
            return RoleAuthorizationFactory.RoleAuthorization(role)

        return None

@injectable()
@order(0)
class TokenAuthorizationFactory(AbstractAuthorizationFactory):
    """
    An `AuthorizationFactory` that will add the logic to verify jwt tokens
    """
    # local class

    class TokenAuthorization(AuthorizationManager.Authorization):
        # constructor

        def __init__(self, session_manager: SessionManager, token_manager: TokenManager):
            self.session_manager = session_manager
            self.token_manager = token_manager

        # internal

        def extract_token_from_request(self, request: HttpRequest) -> str:
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="Missing token",
                                    headers={
                                        "WWW-Authenticate": 'Bearer error="invalid_token", error_description="missing token"'}
                                    )

            return auth_header.split(" ")[1]

        # implement

        def authorize(self, invocation: Invocation):
            http_request = RequestContext.get_request()

            if http_request is not None:
                token = self.extract_token_from_request(http_request)

                session = self.session_manager.read_session(token)
                if session is None:
                    # verify token

                    payload = self.token_manager.decode_jwt(token)

                    # create session

                    session = self.session_manager.create_session(payload)

                    expiry = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
                    self.session_manager.store_session(token, session, expiry)

                # set thread local

                TokenContext.set(token)
                SessionContext.set(session)

    # constructor

    def __init__(self, session_manager: SessionManager, token_manager: TokenManager):
        super().__init__()

        self.token_authorization = TokenAuthorizationFactory.TokenAuthorization(session_manager, token_manager)

    # implement

    def compute_authorization(self, method_descriptor: TypeDescriptor.MethodDescriptor) -> Optional[AuthorizationManager.Authorization]:
        return self.token_authorization

@advice
@injectable()
class RetryAdvice:
    """
    Add aspects that implement a  retry logic, also covering token refresh
    """
    # constructor

    def __init__(self, token_manager: TokenManager):
        self.max_attempts = 3
        self.backoff_base = 0.2
        self.token_manager = token_manager

    # inject

    @inject_value("channel.max_attempts", 3)
    def set_max_attempts(self, max_attempts: int):
        self.max_attempts = max_attempts

    @inject_value("channel.backoff_base", 0.2)
    def set_backoff_base(self, backoff_base: float):
        self.backoff_base = backoff_base

    # sending side

    def refresh_token_if_possible(self):
        refresh_token = TokenContext.get_refresh_token()
        if not refresh_token:
            raise TokenExpiredException("No refresh token available")

        new_access_token = self.token_manager.refresh_access_token(refresh_token)
        TokenContext.set(new_access_token)

    @around(methods().of_type(HTTPXChannel).named("request"))
    def retry_request(self, invocation: Invocation):
        for attempt in range(1, self.max_attempts + 1):
            try:
                return invocation.proceed()

            except TokenExpiredException:
                if attempt == self.max_attempts:
                    raise
                self.refresh_token_if_possible()

            except ServiceCommunicationException:
                ServiceManager.logger.warning(f"Request failed ({invocation.func.__name__}), attempt {attempt}/{self.max_attempts}")

                if attempt == self.max_attempts:
                    raise

                time.sleep(self.backoff_base * (2 ** (attempt - 1)))

        # make the compiler happy

        return None

    @around(methods().of_type(HTTPXChannel).named("request_async"))
    async def retry_async_request(self, invocation: Invocation):
        for attempt in range(1, self.max_attempts + 1):
            try:
                return await invocation.proceed_async()

            except TokenExpiredException as e:
                if attempt == self.max_attempts:
                    raise

                self.refresh_token_if_possible()

            except ServiceCommunicationException:
                ServiceManager.logger.warning(f"Request failed ({invocation.func.__name__}), attempt {attempt}/{self.max_attempts}")

                if attempt == self.max_attempts:
                    raise

                time.sleep(self.backoff_base * (2 ** (attempt - 1)))

        return None

@advice
@injectable()
class AuthorizationAdvice:
    """
    This advice adds the appropriate aspects for services annotated with `@secure`
    """
    # constructor

    def __init__(self, authorization_manager: AuthorizationManager, session_manager: SessionManager):
        self.authorization_manager = authorization_manager

        session_manager.set_factory(lambda token: UserSession(user=token.get("sub"), roles=token.get("roles")))

    # internal

    def authorize(self, invocation: Invocation):
        try:
            self.authorization_manager.authorize(invocation)
        except AuthorizationException as e:
            ServiceManager.logger.warning(f"Authorization failed ({invocation.func.__name__}): {str(e)}")

            raise HTTPException(status_code=403, detail=str(e) + f" in function {invocation.func.__name__}")

    # aspects

    @around(methods().that_are_async().decorated_with(secure),
            methods().that_are_async().declared_by(classes().decorated_with(secure)))
    async def authorize_async(self, invocation: Invocation):
        try:
            self.authorize(invocation)

            return await invocation.proceed_async()
        finally:
            SessionContext.clear()
            TokenContext.clear()

    @around(methods().that_are_sync().decorated_with(secure),
            methods().that_are_sync().declared_by(classes().decorated_with(secure)))
    def authorize_sync(self, invocation: Invocation):
        try:
            self.authorize(invocation)

            return invocation.proceed()
        finally:
            SessionContext.clear()
            TokenContext.clear()

# some services

@service(description="login service")
class LoginService(Service):
    @abstractmethod
    def login(self, user: str, password: str) -> Optional[dict]:
        pass

    @abstractmethod
    def logout(self):
        pass

@service(description="secured service")
@secure()
class SecureService(Service):
    @abstractmethod
    def secured(self):
        pass

    @abstractmethod
    def secured_admin(self):
        pass

@component(name="login-component", services=[LoginService, SecureService])
class JWTComponent(Component): # pylint: disable=abstract-method
    pass

@implementation()
class LoginServiceImpl(LoginService):
    def __init__(self, token_manager: TokenManager):
        self.token_manager = token_manager
        self.users = {
            "hugo": {
                "username": "hugo",
                "password": "secret",
                "roles": ["user"]
            },
            "andi": {
                "username": "andi",
                "password": "secret",
                "roles": ["user", "admin"]
            }
        }

    def login(self, user: str, password: str) -> Optional[dict]:
        profile = self.users.get(user, None)
        if profile is not None and profile.get("password") == password:
            access_token = self.token_manager.create_access_token(user, profile.get("roles"))
            refresh_token = self.token_manager.create_refresh_token(user, profile.get("roles"))

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
            }

        return None

    def logout(self):
        pass

@implementation()
@secure()
class SecureServiceServiceImpl(SecureService):
    def __init__(self):
        pass

    def secured(self):
        session = SessionContext.get(UserSession)

    @requires_role("admin")
    def secured_admin(self):
        session = SessionContext.get(UserSession)


@implementation()
@health("/jwt-health")
class JWTComponentImpl(AbstractComponent, JWTComponent):
    # constructor

    def __init__(self):
        super().__init__()

    # implement

    def get_addresses(self, port: int) -> list[ChannelAddress]:
        return [
            ChannelAddress("dispatch-json", f"http://{Server.get_local_ip()}:{port}"),
            ChannelAddress("dispatch-msgpack", f"http://{Server.get_local_ip()}:{port}")
        ]

class TestLocalService():
    def test_login(self, service_manager):
        login_service = service_manager.get_service(LoginService, preferred_channel="dispatch-json")

        secure_service = service_manager.get_service(SecureService, preferred_channel="dispatch-json")

        try:
            secure_service.secured()
        except Exception as e:
            print(e)

        tokens = login_service.login("hugo", "secret")

        with TokenContext.use(tokens["access_token"], tokens["refresh_token"]):
            secure_service.secured()

            try:
                secure_service.secured_admin()
            except Exception as e:
                print(e)

            login_service.logout()

            TokenContext.clear()

            # now andi

            tokens = login_service.login("andi", "secret")

            TokenContext.set(tokens["access_token"], tokens["refresh_token"])

            secure_service.secured_admin()
