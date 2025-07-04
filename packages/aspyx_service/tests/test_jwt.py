import logging
from typing import Optional, cast, Dict

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

from abc import abstractmethod


import httpx
import jwt
import datetime

from aspyx.reflection import Decorators



from aspyx.di import injectable
from aspyx.di.aop import advice, around, Invocation, methods, classes
from aspyx_service import Service, service, component, implementation, AbstractComponent, \
    DispatchJSONChannel, Component, ChannelAddress, Server, health, RequestContext

from .common import service_manager

from fastapi import Request as HttpRequest, HTTPException

SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# in-memory user "database"

fake_users_db = {
    "andi": {
        "username": "andi",
        "password": "secret",  # For demo only – use hashing in real apps!
    }
}

def create_jwt(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1),
        "iat": datetime.datetime.utcnow(),
        "roles": ["user"]
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

    return token

def verify_jwt(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload  # token is valid
    except jwt.ExpiredSignatureError:
        print("Token expired")
    except jwt.InvalidTokenError:
        print("Invalid token")
    return None

# channel stuff

@injectable()
class TokenProvider:
    def __init__(self):
        self.token : Optional[str] = None

    def set_token(self, token: str):
        self.token = token

    def provide_token(self) -> Optional[str]:
        return self.token


class InterceptingClient(httpx.Client):
    # constructor

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.token_provider : Optional[TokenProvider] = None

    # override

    def request(self, method, url, *args, **kwargs):
        token = None
        if self.token_provider is not None:
            token = self.token_provider.provide_token()

        if token is not None:
            headers = kwargs.pop("headers", {})
            if headers is None: # None is also valid!
                headers = {}

            ## add bearer token

            headers["Authorization"] = f"Bearer {token}"
            kwargs["headers"] = headers

        return super().request(method, url, *args, **kwargs)

# decorator

def secure():
    def decorator(cls):
        Decorators.add(cls, secure)

        return cls

    return decorator

# advice

@advice
class ChannelAdvice:
    # constructor

    def __init__(self, token_provider: TokenProvider):
        self.token_provider = token_provider

    # internal

    def extract_token_from_request(self, request: HttpRequest) -> str:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid token")

        return auth_header.split(" ")[1]

    def verify_token(self, http_request: HttpRequest):
        token = self.extract_token_from_request(http_request)
        ok = verify_jwt(token)
        if ok is None:
            raise HTTPException(status_code=401, detail="Invalid token")

    # aspects

    @around(methods().named("make_client").of_type(DispatchJSONChannel))
    def make_client(self, invocation: Invocation):
        intercepting_client = InterceptingClient()

        intercepting_client.token_provider = self.token_provider

        return intercepting_client

    @around(classes().decorated_with(secure))
    def check_jwt(self, invocation: Invocation):
        print("check jwt")
        # local method

        http_request = RequestContext.get_request()

        if http_request is not None:
            self.verify_token(http_request)

        return invocation.proceed()

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
        pass

    def login(self, user: str, password: str) -> Optional[str]:
        profile = fake_users_db.get(user, None)
        if profile is not None:
            if profile.get("password") == password:
                return create_jwt(user)
            else:
                return None
        else:
            return None

@implementation()
@secure()
class SecureServiceServiceImpl(SecureService):
    def __init__(self):
        pass

    def secured(self):
        pass


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
        token_provider = service_manager.environment.get(TokenProvider)

        token = login_service.login("andi", "secret")

        token_provider.set_token(token)

        secure_service.secured()

        print("hmmm")
