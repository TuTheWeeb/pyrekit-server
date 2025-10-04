import inspect
import logging
from functools import wraps
from multiprocessing import Process
from typing import Any, Dict, List, Tuple

from flask import Flask
from flask_cors import CORS
from waitress import serve

ROUTE = Tuple[str, str, Dict[str, List[str]]]


def function_to_rule(name: str, prefix: str) -> str:
    """
    Change the _ to / in the route, so that the route can work
    """

    path = name[len(prefix) :]

    return f"/{path.replace('_', '/')}"


def parse_route(name: str) -> Tuple[str | None, str]:
    """
    Parse the route from the method name
    """

    HTTP_PREFIX_MAP = {
        "GET_": "GET",
        "POST_": "POST",
        "PUT_": "PUT",
        "DELETE_": "DELETE",
    }

    for prefix, method in HTTP_PREFIX_MAP.items():
        if name.startswith(prefix):
            return method, function_to_rule(name, prefix)
    return None, ""


def parse_arguments(value: Any) -> str:
    """
    Parse the methods arguments to be added to the route of the request
    """

    sig = inspect.signature(value)
    TYPE_CONVERTER_MAP = {
        int: "int",
        float: "float",
        str: "str",
    }
    converter = lambda val: TYPE_CONVERTER_MAP.get(val, "str")

    # filter out the self argument
    parameters = filter(lambda x: x.name != "self", sig.parameters.values())

    # maps each paramenter to a tuple (name, type)
    parameters = map(
        lambda param: (param.name, converter(param.annotation)), parameters
    )

    parameters = [
        f"/<{param[0]}>" if param[1] == "str" else f"/<{param[1]}:{param[0]}>"
        for param in parameters
    ]

    return "".join(parameters)


def parse_routes(attrs: Dict[str, Any]) -> List[ROUTE]:
    """
    Parse all the functions and returns a list with all the routes in the class
    """

    routes_to_register: List[ROUTE] = []

    for name, value in attrs.items():
        if not callable(value) or name.startswith("_"):
            continue
        if name == "index":
            rule = "/"
            http_methods = ["GET", "POST"]
            routes_to_register.append((rule, "index", {"methods": http_methods}))
            continue

        found_method, rule = parse_route(name)

        if found_method:
            rule += parse_arguments(value)

            routes_to_register.append((rule, name, {"methods": [found_method]}))

    return routes_to_register


class MetaServer(type):
    """
    Used as a metaclass, to create the routes of the server
    """

    def __init__(cls, name, bases, attrs: dict[str, Any]):
        super().__init__(name, bases, attrs)

        # Register the routes_info to the object
        cls.routes_info: List[ROUTE] = parse_routes(attrs)

        if not cls.routes_info:
            return

        original_init = cls.__init__

        @wraps(original_init)
        def wrapped_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            for rule, name, options in cls.routes_info:
                view_func = getattr(self, name)
                endpoint = options.pop("endpoint", name)

                self.add_url_rule(
                    rule, endpoint=endpoint, view_func=view_func, **options
                )

        cls.__init__ = wrapped_init  # type: ignore


class Server(Flask, metaclass=MetaServer):
    """
    A Base server that should not be used alone, it must be inherited to be used
    """

    def __init__(self, port=8000, host="0.0.0.0", threads: int = 4, **kwargs):
        super().__init__(import_name=__name__, **kwargs)
        CORS(self)

        self.port = port
        self.host = host
        self.threads = threads
        self.limit = 100 if 100 > threads else threads + 3

        for rule, name, options in self.routes_info:
            print(rule, name, options)

        logger = logging.getLogger("waitress")
        logger.setLevel(logging.INFO)

    def start(self):
        try:
            serve(
                self,
                threads=self.threads,
                connection_limit=self.limit,
                host=self.host,
                port=self.port,
            )
        except:
            # If the port is already in use it gets the next one
            print(
                "Port:", self.port, "already in use, using the next one:", self.port + 1
            )
            self.port += 1
            serve(
                self,
                threads=self.threads,
                connection_limit=self.limit,
                host=self.host,
                port=self.port,
            )


class ServerProcess(Process):
    """
    A Process used to start and end the the Server
    """

    def __init__(self, app: Server, daemon=False, **kwargs) -> None:
        target = app.start
        super().__init__(kwargs=kwargs, target=target, daemon=daemon)

    def stop(self):
        super().close()
        super().join()
