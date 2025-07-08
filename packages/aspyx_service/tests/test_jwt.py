"""
jwt sample test
"""
import faulthandler
import time

from aspyx.util import ConfigureLogger

faulthandler.enable()

from typing import Optional, Dict, Callable

import logging
from abc import abstractmethod

from fastapi import Request as HttpRequest, HTTPException

from datetime import datetime, timezone, timedelta

ConfigureLogger(default_level=logging.DEBUG, levels={
    "httpx": logging.ERROR,
    "aspyx.di": logging.ERROR,
    "aspyx.di.aop": logging.ERROR,
    "aspyx.service": logging.ERROR
})

from aspyx_service import Service, service, component, implementation, AbstractComponent, \
    Component, ChannelAddress, Server, health, RequestContext, HTTPXChannel, \
    AbstractAuthorizationFactory, AuthorizationManager, SessionManager, AuthorizationException, Session, \
    ServiceCommunicationException, TokenExpiredException

from aspyx.reflection import Decorators, TypeDescriptor

from aspyx.di import injectable
from aspyx.di.aop import advice, around, Invocation, methods, classes


from .common import service_manager, TokenManager


# decorator

def secure():
    def decorator(cls):
        Decorators.add(cls, secure)

        return cls

    return decorator

# session

class UserSession(Session):
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
class RoleAuthorizationFactory(AbstractAuthorizationFactory):
    # local class

    class RoleAuthorization(AuthorizationManager.Authorization):
        # constructor

        def __init__(self, role: str):
            self.role = role

        # implement

        def check(self):
            if not self.role in SessionManager.current(UserSession).roles:
                raise AuthorizationException(f"expected role {self.role}")
    # implement

    def compute_authorization(self, method_descriptor: TypeDescriptor.MethodDescriptor) -> Optional[AuthorizationManager.Authorization]:
        if method_descriptor.has_decorator(requires_role):
            role = method_descriptor.get_decorator(requires_role).args[0]
            return RoleAuthorizationFactory.RoleAuthorization(role)

        return None

@advice
@injectable()
class RetryAdvice:
    # constructor

    def __init__(self):
        self.max_attempts = 3
        self.backoff_base = 0.2

    # sending side

    @around(methods().of_type(HTTPXChannel).named("request"))
    def retry_request(self, invocation: Invocation):
        for attempt in range(1, self.max_attempts + 1):
            try:
                return invocation.proceed()

            except AuthorizationException as e:
                raise

            except TokenExpiredException as e:
                raise# TODO

            except ServiceCommunicationException:
                #logger.warning(f"Request failed ({type(e).__name__}), attempt {attempt}/{max_attempts}")

                if attempt == self.max_attempts:
                    raise

                time.sleep(self.backoff_base * (2 ** (attempt - 1)))

        return None

    @around(methods().of_type(HTTPXChannel).named("request_async"))
    async def retry_async_request(self, invocation: Invocation):
        for attempt in range(1, self.max_attempts + 1):
            try:
                return await invocation.proceed_async()

            except TokenExpiredException as e:
                raise  # TODO

            except ServiceCommunicationException:
                # logger.warning(f"Request failed ({type(e).__name__}), attempt {attempt}/{max_attempts}")

                if attempt == self.max_attempts:
                    raise

                time.sleep(self.backoff_base * (2 ** (attempt - 1)))

        return None

@advice
@injectable()
class AuthenticationAndAuthorizationAdvice:
    # constructor

    def __init__(self, authorization_manager: AuthorizationManager, session_manager: SessionManager, token_manager: TokenManager):
        self.session_manager = session_manager
        self.token_manager = token_manager
        self.authorization_manager = authorization_manager
        self.session_manager.set_session_factory(lambda token:
                                             UserSession(user=token.get("sub"), roles=token.get("roles")))

        # sender
        self.max_attempts = 3
        self.backoff_base = 0.2

    # internal

    def extract_token_from_request(self, request: HttpRequest) -> str:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing token",
                                headers={
                                    "WWW-Authenticate": 'Bearer error="invalid_token", error_description="missing token"'}
                                )

        return auth_header.split(" ")[1]

    def check_session(self, func: Callable):
        http_request = RequestContext.get_request()

        if http_request is not None:
            token = self.extract_token_from_request(http_request)

            session = self.session_manager.get_session(token)
            if session is None:
                # verify token

                payload = self.token_manager.decode_jwt(token)

                # create session object

                session = self.session_manager.create_session(payload)

                expiry = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
                self.session_manager.store_session(token, session, expiry)

            # set thread local

            SessionManager.set_session(session)

        # authorization?

        try:
            for check in self.authorization_manager.get_checks(func):
                check.check()
        except AuthorizationException as e:
            raise HTTPException(status_code=403, detail=str(e) + f" in function {func.__name__}")

    # aspects

    @around(methods().that_are_async().decorated_with(secure),
            methods().that_are_async().declared_by(classes().decorated_with(secure)))
    async def check_async_authentication(self, invocation: Invocation):
        try:
            self.check_session(invocation.func)

            return await invocation.proceed_async()
        finally:
            SessionManager.delete_session()

    @around(methods().that_are_sync().decorated_with(secure),
            methods().that_are_sync().declared_by(classes().decorated_with(secure)))
    def check_authentication(self, invocation: Invocation):
        try:
            self.check_session(invocation.func)

            return invocation.proceed()
        finally:
            SessionManager.delete_session()

# some services

@service(description="login service")
class LoginService(Service):
    @abstractmethod
    def login(self, user: str, password: str) -> Optional[str]:
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

    def login(self, user: str, password: str) -> Optional[str]:
        profile = self.users.get(user, None)
        if profile is not None and profile.get("password") == password:
            return self.token_manager.create_jwt(user, profile.get("roles"))

        return None

    def logout(self):
        pass

@implementation()
@secure()
class SecureServiceServiceImpl(SecureService):
    def __init__(self):
        pass

    def secured(self):
        session = SessionManager.current(UserSession)

    @requires_role("admin")
    def secured_admin(self):
        session = SessionManager.current(UserSession)


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

        token = login_service.login("hugo", "secret")

        HTTPXChannel.remember_token(login_service, token)

        secure_service.secured()

        try:
            secure_service.secured_admin()
        except Exception as e:
            print(e)

        login_service.logout()

        HTTPXChannel.clear_token(login_service, token)

        # now andi

        token = login_service.login("andi", "secret")

        HTTPXChannel.remember_token(login_service, token)

        secure_service.secured_admin()
