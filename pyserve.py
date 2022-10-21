import argparse
import asyncio
import asyncio.subprocess
import atexit
import cgi
import dataclasses
import io
import logging
import os
import sys
import tempfile
import urllib.parse
from http import HTTPStatus
from http.cookies import SimpleCookie
from typing import Any

__version__ = "0.1.0"

logger = logging.getLogger("pyserve")

logger_handler = logging.StreamHandler(sys.stdout)
logger_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))

logger.addHandler(logger_handler)
logger.setLevel(logging.INFO)


CRLF = "\r\n"
B_CRLF = b"\r\n"

SOFTWARE = "PyServe"
HTTP_VERSION = "HTTP/1.1"


def get_body_params() -> dict[str, list[str]]:
    fields = cgi.FieldStorage(environ={**os.environ, "REQUEST_METHOD": "POST"})
    return {key: fields.getlist(key) for key in fields.keys()}


def get_url_params() -> dict[str, list[str]]:
    return urllib.parse.parse_qs(os.environ.get("QUERY_STRING", ""))


def get_cookies() -> dict[str, str]:
    return {
        k: v.value
        for k, v in SimpleCookie[str](os.environ.get("HTTP_COOKIE", "")).items()
    }


@dataclasses.dataclass(frozen=True)
class Http:
    COOKIE: dict[str, str]
    GET: dict[str, list[str]]
    HEADER: dict[str, str]
    POST: dict[str, list[str]]
    STATUS: HTTPStatus


http = Http(
    HEADER={
        "Content-Type": "text/html",
    },
    GET={},
    POST={},
    COOKIE={},
    STATUS=HTTPStatus.OK,
)

_stdout = io.StringIO()

_server: asyncio.Server | None = None

_args: argparse.Namespace | None = None


HttpHeaders = dict[str, str]


@dataclasses.dataclass(frozen=True)
class HttpMessage:
    http_version: str
    headers: HttpHeaders
    body: bytes


@dataclasses.dataclass(frozen=True)
class HttpRequest(HttpMessage):
    method: str
    target: str


@dataclasses.dataclass(frozen=True)
class HttpResponse(HttpMessage):
    status: int
    message: str


async def parse_http_header_fields(reader: asyncio.StreamReader) -> HttpHeaders:
    headers = {}

    while (line := await reader.readline()) != B_CRLF:
        field_name, field_value = line.rstrip(B_CRLF).split(b":", maxsplit=1)
        headers[field_name.decode()] = field_value.strip().decode()

    return headers


def build_http_header_fields(headers: HttpHeaders) -> str:
    header_fields = ""

    for key, value in headers.items():
        header_fields += f"{key}: {value}{CRLF}"

    return header_fields


async def parse_http_request(reader: asyncio.StreamReader) -> HttpRequest | None:
    # request line
    if line := await reader.readline():
        method, target, http_version = line.rstrip(B_CRLF).split(maxsplit=2)

        # header fields
        headers = await parse_http_header_fields(reader)

        # get content length
        content_length = int(headers.get("Content-Length", 0))

        # body
        body = await reader.read(content_length)

        return HttpRequest(
            method=method.decode(),
            target=target.decode(),
            http_version=http_version.decode(),
            headers=headers,
            body=body,
        )

    return None


def build_http_request(http_request: HttpRequest) -> bytes:
    request = (
        f"{http_request.method} {http_request.target} {http_request.http_version}{CRLF}"
    )
    request += build_http_header_fields(http_request.headers)
    request += CRLF

    return request.encode() + http_request.body


async def parse_http_response(reader: asyncio.StreamReader) -> HttpResponse | None:
    # status line
    if line := await reader.readline():
        http_version, status, message = line.rstrip(B_CRLF).split(maxsplit=2)

        # header fields
        headers = await parse_http_header_fields(reader)

        # body
        body = await reader.read()

        # update content length
        if "Content-Length" not in headers:
            headers["Content-Length"] = f"{len(body)}"

        return HttpResponse(
            http_version=http_version.decode(),
            status=int(status),
            message=message.decode(),
            headers=headers,
            body=body,
        )

    return None


def build_http_response(http_response: HttpResponse) -> bytes:
    response = f"{http_response.http_version} {http_response.status} {http_response.message}{CRLF}"
    response += build_http_header_fields(http_response.headers)
    response += CRLF

    return response.encode() + http_response.body


def get_extra_info(reader: asyncio.StreamReader, name: str) -> Any:
    # the _transport attribute is not part of the public API
    return reader._transport.get_extra_info(name)  # type: ignore[attr-defined]


def prepare_env(
    request: HttpRequest,
    **extra: str,
) -> dict[str, str]:
    host, port, workdir = _args.host, str(_args.port), _args.workdir  # type: ignore[union-attr]

    env = {
        **os.environ,
        "REQUEST_METHOD": request.method,
        "SERVER_ADDR": host,
        "SERVER_PORT": port,
        "SERVER_PROTOCOL": HTTP_VERSION,
        "SERVER_ROOT": workdir,
        "SERVER_SOFTWARE": SOFTWARE,
    }

    if "QUERY_STRING" in extra:
        env["QUERY_STRING"] = extra["QUERY_STRING"]

    if "REMOTE_ADDR" in extra:
        env["REMOTE_ADDR"] = extra["REMOTE_ADDR"]

    http_headers = {
        "Accept": "HTTP_ACCEPT",
        "Connection": "HTTP_CONNECTION",
        "Content-Length": "CONTENT_LENGTH",
        "Content-Type": "CONTENT_TYPE",
        "Cookie": "HTTP_COOKIE",
        "Host": "HTTP_HOST",
        "Pragma": "HTTP_PRAGMA",
        "Referer": "HTTP_REFERER",
        "User-Agent": "HTTP_USER_AGENT",
    }

    for header, env_ in http_headers.items():
        if header in request.headers:
            env[env_] = request.headers[header]

    return env


async def client_handler(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    workdir = _args.workdir  # type: ignore[union-attr]

    while True:
        request = await parse_http_request(reader)
        if request is None:
            break

        logger.info(request)

        peer_name = get_extra_info(reader, "peername")

        url = urllib.parse.urlsplit(request.target)

        script_name = url.path.removeprefix("/")
        script_name = os.path.realpath(script_name)
        if not script_name.startswith(workdir):
            raise RuntimeError(f"Invalid script path")

        with tempfile.NamedTemporaryFile("w+b") as temp_fp:
            temp_fp.write(request.body)
            temp_fp.flush()
            temp_fp.seek(0)

            env = prepare_env(request, QUERY_STRING=url.query, REMOTE_ADDR=peer_name[0])

            script_process = await asyncio.subprocess.create_subprocess_exec(
                script_name,
                stdin=temp_fp,
                stdout=asyncio.subprocess.PIPE,
                env=env,
            )

            if script_process.stdout is None:
                raise RuntimeError("stdout is None")

            response = await parse_http_response(script_process.stdout)
            logger.info(response)

            await script_process.wait()

        writer.write(build_http_response(response))
        await writer.drain()

        if request.headers.get("Connection") != "keep-alive":
            writer.close()
            break


async def start_server(host: str, port: int) -> None:
    global _server

    _server = await asyncio.start_server(
        client_handler, host, port, reuse_address=True, reuse_port=True
    )

    logger.info(f"Server started on {host}:{port}")

    await _server.serve_forever()


async def stop_server() -> None:
    if _server is not None:
        _server.close()
        await _server.wait_closed()

        logger.info("Server stopped")


def init() -> None:
    sys.stdout = _stdout

    def flush_stdout():
        response = HttpResponse(
            http_version=HTTP_VERSION,
            status=http.STATUS.value,
            message=http.STATUS.phrase,
            headers=http.HEADER,
            body=_stdout.getvalue().encode(),
        )

        sys.stdout = sys.__stdout__

        sys.stdout.write(build_http_response(response).decode())
        sys.stdout.flush()

    atexit.register(flush_stdout)

    if os.environ.get("REQUEST_METHOD") == "GET":
        http.GET.update(get_url_params())

    if os.environ.get("REQUEST_METHOD") == "POST":
        http.POST.update(get_body_params())

    if os.environ.get("HTTP_COOKIE"):
        http.COOKIE.update(get_cookies())


async def main() -> None:
    global _args

    arg_parser = argparse.ArgumentParser(f"PyServe v{__version__}")
    arg_parser.add_argument("--host", default="127.0.0.1")
    arg_parser.add_argument("--port", default=8000, type=int)
    arg_parser.add_argument("--workdir", default=os.getcwd())

    _args = arg_parser.parse_args()

    await start_server(_args.host, _args.port)


if __name__ == "__main__":
    asyncio.run(main())
else:
    if "PYTEST_CURRENT_TEST" not in os.environ:
        init()
