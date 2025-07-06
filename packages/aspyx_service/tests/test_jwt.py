"""
jwt sample test
"""
import faulthandler

faulthandler.enable()

import logging
from abc import abstractmethod
import jwt
from typing import Optional, Dict, Callable
from fastapi import Request as HttpRequest, HTTPException

from datetime import datetime, timezone, timedelta

logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)s in %(filename)s:%(lineno)d - %(message)s'
)

logging.getLogger("httpx").setLevel(logging.INFO)

def configure_logging(levels: Dict[str, int]) -> None:
    for name in levels:
        logging.getLogger(name).setLevel(levels[name])

configure_logging({
    "xaspyx.di": logging.INFO,
    "xaspyx.di.aop": logging.INFO,
    "xaspyx.service": logging.DEBUG
})

from aspyx_service import Service, service, component, implementation, AbstractComponent, \
     Component, ChannelAddress, Server, health, RequestContext, HTTPXChannel, \
    AbstractAnalyzer, AuthorizationManager, SessionManager, AuthorizationException, Session

from aspyx.reflection import Decorators, TypeDescriptor

from aspyx.di import injectable
from aspyx.di.aop import advice, around, Invocation, methods, classes


from .common import service_manager

SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

class TokenManager:
    # constructor

    def __init__(self, secret: str, algorithm: str):
        self.secret = secret
        self.algorithm = algorithm

    # methods

    def create_jwt(self, user_id: str, roles: list[str]) -> str:
        payload = {
            "sub": user_id,
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow(),
            "roles": roles
        }
        token = jwt.encode(payload, self.secret, algorithm=self.algorithm)

        return token

    def verify_jwt(self, token: str):
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])

            return payload  # token is valid
        except jwt.ExpiredSignatureError:
            print("Token expired")
        except jwt.InvalidTokenError:
            print("Invalid token")

        return None

token_manager = TokenManager(SECRET_KEY, ALGORITHM)

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
    Methods decorated with `@around` will be executed around the target method.
    Every around method must accept a single parameter of type Invocation and needs to call proceed
    on this parameter to proceed to the next around method.
    """
    def decorator(func):
        Decorators.add(func, requires_role, role)

        return func

    return decorator


@injectable()
class RoleAnalyzer(AbstractAnalyzer):
    # local class

    class RoleCheck(AuthorizationManager.Check):
        # constructor

        def __init__(self, role: str):
            self.role = role

        # implement

        def check(self):
            if not self.role in SessionManager.current(UserSession).roles:
                raise AuthorizationException(f"expected role {self.role}")
    # implement

    def compute_check(self, method_descriptor: TypeDescriptor.MethodDescriptor) -> Optional['AuthorizationManager.Check']:
        if method_descriptor.has_decorator(requires_role):
            role = method_descriptor.get_decorator(requires_role).args[0]
            return RoleAnalyzer.RoleCheck(role)

        return None

@advice
@injectable()
class AuthenticationAndAuthorizationAdvice:
    # constructor

    def __init__(self, authorization_manager: AuthorizationManager, session_manager: SessionManager):
        self.session_manager = session_manager
        self.authorization_manager = authorization_manager
        self.session_manager.set_session_creator(lambda token:
                                             UserSession(user=token.get("sub"), roles=token.get("roles")))

    # internal

    def extract_token_from_request(self, request: HttpRequest) -> str:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid token")

        return auth_header.split(" ")[1]

    def verify_token(self, token: str) -> dict:
        payload = token_manager.verify_jwt(token)
        if payload is None:
            raise HTTPException(status_code=401, detail="Invalid token")

        return payload

    def check_session(self, func: Callable):
        http_request = RequestContext.get_request()

        if http_request is not None:
            token = self.extract_token_from_request(http_request)

            session = self.session_manager.get_session(token)
            if session is None:
                # verify token

                payload = self.verify_token(token)

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
        self.check_session(invocation.func)

        # continue wih established session

        try:
            return await invocation.proceed_async()
        finally:
            SessionManager.delete_session()

    @around(methods().that_are_sync().decorated_with(secure), methods().that_are_sync().declared_by(classes().decorated_with(secure)))
    def check_authentication(self, invocation: Invocation):
        self.check_session(invocation.func)

        # continue wih established session

        try:
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
    def __init__(self):
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
            return token_manager.create_jwt(user, profile.get("roles"))

        return None

    def logout(self):
        pass

@implementation()
@secure()
class SecureServiceServiceImpl(SecureService):
    def __init__(self):
        print("create SecureServiceServiceImpl")
        pass

    def secured(self):
        session = SessionManager.current(UserSession)

        print(session.user)

    @requires_role("admin")
    def secured_admin(self):
        session = SessionManager.current(UserSession)

        print(session.user)


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
