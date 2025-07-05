"""
jwt sample test
"""
import faulthandler; faulthandler.enable()

import inspect
import logging
from abc import abstractmethod
import httpx
import jwt
import datetime
from typing import Optional, cast, Dict, Any, TypeVar, Type
from fastapi import Request as HttpRequest, HTTPException

from aspyx.threading import ThreadLocal

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
    DispatchJSONChannel, Component, ChannelAddress, Server, health, RequestContext, HTTPXChannel, remember_token

from aspyx.reflection import Decorators



from aspyx.di import injectable
from aspyx.di.aop import advice, around, Invocation, methods, classes


from .common import service_manager

SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def get_method_class(method):
    if inspect.ismethod(method) or inspect.isfunction(method):
        qualname = method.__qualname__
        parts = qualname.split('.')
        if len(parts) > 1:
            cls_name = parts[-2]
            module = inspect.getmodule(method)
            if module:
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if name == cls_name and hasattr(obj, method.__name__):
                        return obj
    return None

class TokenManager:
    def __init__(self, secret: str, algorithm: str):
        self.secret = secret
        self.algorithm = algorithm

    def create_jwt(self, user_id: str) -> str:
        payload = {
            "sub": user_id,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1),
            "iat": datetime.datetime.utcnow(),
            "roles": ["user"]
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

class Session:
    def __init__(self):
        pass

class UserSession(Session):
    def __init__(self, user: str, roles: list[str]):
        super().__init__()

        self.user = user
        self.roles = roles

T = TypeVar("T")

#@injectable()
class SessionManager:
    current_session = ThreadLocal[Session]()
    sessions : dict[str, Session] = {}

    @classmethod
    def current(cls, type: Type[T]) -> T:
        return cls.current_session.get()

    @classmethod
    def set_session(cls, session: Session):
        cls.current_session.set(session)

    @classmethod
    def delete_session(cls):
        cls.current_session.clear()

    # constructor

    def __init__(self):
        pass

# advice

@advice
class ChannelAdvice:
    # constructor

    def __init__(self):# TODO ??? , session_manager: SessionManager):
        self.session_manager = SessionManager()

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

    # aspects

    # TODO that_are_sync...

    @around(classes().decorated_with(secure))
    def check_authentication(self, invocation: Invocation):
        http_request = RequestContext.get_request()

        if http_request is not None:
            token = self.extract_token_from_request(http_request)

            session = self.session_manager.sessions.get(token, None)
            if session is None:
                # TODO LRU, expiry, etc...

                # verify token

                payload = self.verify_token(token)

                # create session object

                session = UserSession(payload["sub"], payload["roles"])

                SessionManager.sessions[token] = session

            # set thread local

            SessionManager.set_session(session)

        # test

        # check method and class

        method = invocation.func
        clazz = get_method_class(method)



        # test

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

@service(description="secured service")
@secure()
class SecureService(Service):
    @abstractmethod
    def secured(self):
        pass


@component(name="login-component", services=[LoginService, SecureService])
class JWTComponent(Component): # pylint: disable=abstract-method
    pass

@implementation()
class LoginServiceImpl(LoginService):
    def __init__(self):
        self.users ={
            "andi": {
                "username": "andi",
                "password": "secret",
            }
        }

    def login(self, user: str, password: str) -> Optional[str]:
        profile = self.users.get(user, None)
        if profile is not None and profile.get("password") == password:
            return token_manager.create_jwt(user)

        return None

@implementation()
@secure()
class SecureServiceServiceImpl(SecureService):
    def __init__(self):
        pass

    def secured(self):
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

        token = login_service.login("andi", "secret")

        remember_token(login_service, token)

        secure_service.secured()

        print("hmmm")
