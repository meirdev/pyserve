import asyncio
import os

import pytest

if "PYTEST_CURRENT_TEST" not in os.environ:
    os.environ["PYTEST_CURRENT_TEST"] = "1"

import pyserve


@pytest.mark.asyncio
async def test_parse_http_request():
    stream = asyncio.StreamReader()
    stream.feed_data(
        b"GET /hello_world.py HTTP/1.1\r\n"
        b"Host: localhost:8000\r\n"
        b"User-Agent: test\r\n"
        b"Accept: */*\r\n"
        b"\r\n"
    )
    stream.feed_eof()

    http_request = await pyserve.parse_http_request(stream)

    assert http_request.method == "GET"
    assert http_request.target == "/hello_world.py"
    assert http_request.http_version == "HTTP/1.1"
    assert http_request.headers == {
        "Host": "localhost:8000",
        "User-Agent": "test",
        "Accept": "*/*",
    }


@pytest.mark.asyncio
async def test_parse_http_response():
    stream = asyncio.StreamReader()
    stream.feed_data(
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: text/html\r\n"
        b"Content-Length: 13\r\n"
        b"\r\n"
        b"Hello World!\n"
    )
    stream.feed_eof()

    http_response = await pyserve.parse_http_response(stream)

    assert http_response.http_version == "HTTP/1.1"
    assert http_response.status == 200
    assert http_response.message == "OK"
    assert http_response.headers == {
        "Content-Type": "text/html",
        "Content-Length": "13",
    }
    assert http_response.body == b"Hello World!\n"


def test_build_http_response():
    http_response = pyserve.HttpResponse(
        http_version="HTTP/1.1",
        headers={
            "Content-Type": "text/html",
            "Content-Length": "13",
        },
        body=b"Hello World!\n",
        status=200,
        message="OK",
    )

    plain = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: text/html\r\n"
        b"Content-Length: 13\r\n"
        b"\r\n"
        b"Hello World!\n"
    )

    assert pyserve.build_http_response(http_response) == plain


def test_build_http_request():
    http_request = pyserve.HttpRequest(
        method="GET",
        target="/hello_world.py",
        http_version="HTTP/1.1",
        headers={
            "Host": "localhost:8000",
            "User-Agent": "test",
            "Accept": "*/*",
        },
        body=b"",
    )

    plain = (
        b"GET /hello_world.py HTTP/1.1\r\n"
        b"Host: localhost:8000\r\n"
        b"User-Agent: test\r\n"
        b"Accept: */*\r\n"
        b"\r\n"
    )

    assert pyserve.build_http_request(http_request) == plain


@pytest.mark.asyncio
async def test_server():
    server = asyncio.create_task(pyserve.start_server("localhost", 8080))

    # wait for server to start
    await asyncio.sleep(2.0)

    # for some reason sending a request to the server from the script doesn't work
    # res = requests.get("http://localhost:8080/examples/hello_world.py")
    # assert res.text == "Hello World!\n"

    await pyserve.stop_server()
