# -*- coding: utf-8 -*-
"""
mureq is a replacement for python-requests, intended to be vendored
in-tree by Linux systems software and other lightweight applications.

mureq is copyright 2021 by its contributors and is released under the
0BSD ("zero-clause BSD") license.
"""
# mypy: ignore-errors
from __future__ import annotations

import contextlib
import io
import os.path
import urllib.parse
from http.client import HTTPConnection
from http.client import HTTPException
from http.client import HTTPMessage
from http.client import HTTPResponse
from http.client import HTTPSConnection
from typing import Generator

from msgspec.json import decode as loads
from msgspec.json import encode as dumps


DEFAULT_TIMEOUT = 15.0
DEFAULT_UA = "Python/Pioreactor"


def basic_auth(username: str, password: str) -> str:
    from base64 import b64encode

    # get(..., headers={ 'Authorization' : f'Basic {basic_auth(username, password)}'})
    token = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return token


def request(method, url, *, read_limit=None, **kwargs) -> Response:
    """request performs an HTTP request and reads the entire response body.

    :param str method: HTTP method to request (e.g. 'GET', 'POST')
    :param str url: URL to request
    :param read_limit: maximum number of bytes to read from the body, or None for no limit
    :type read_limit: int or None
    :param kwargs: optional arguments defined by yield_response
    :return: Response object
    :rtype: Response
    :raises: HTTPException
    """
    with yield_response(method, url, **kwargs) as response:
        try:
            body = response.read(read_limit)
        except HTTPException:
            raise
        except IOError as e:
            raise HTTPException(str(e)) from e
        return Response(
            response.url,  # type: ignore
            response.status,
            _prepare_incoming_headers(response.headers),
            body,
        )


def get(url, **kwargs) -> Response:
    """get performs an HTTP GET request."""
    return request("GET", url=url, **kwargs)


def post(url, body: bytes | None = None, **kwargs) -> Response:
    """post performs an HTTP POST request."""
    return request("POST", url=url, body=body, **kwargs)


def head(url, **kwargs) -> Response:
    """head performs an HTTP HEAD request."""
    return request("HEAD", url=url, **kwargs)


def put(url, body: bytes | None = None, **kwargs) -> Response:
    """put performs an HTTP PUT request."""
    return request("PUT", url=url, body=body, **kwargs)


def patch(url, body: bytes | None = None, **kwargs) -> Response:
    """patch performs an HTTP PATCH request."""
    return request("PATCH", url=url, body=body, **kwargs)


def delete(url, **kwargs) -> Response:
    """delete performs an HTTP DELETE request."""
    return request("DELETE", url=url, **kwargs)


@contextlib.contextmanager
def yield_response(
    method,
    url,
    *,
    unix_socket=None,
    timeout=DEFAULT_TIMEOUT,
    headers=None,
    params: dict | None = None,
    body=None,
    form=None,
    json=None,
    verify=True,
    source_address=None,
    max_redirects=None,
    ssl_context=None,
) -> Generator[HTTPResponse, None, None]:
    """yield_response is a low-level API that exposes the actual
    http.client.HTTPResponse via a contextmanager.

    Note that unlike mureq.Response, http.client.HTTPResponse does not
    automatically canonicalize multiple appearances of the same header by
    joining them together with a comma delimiter. To retrieve canonicalized
    headers from the response, use response.getheader():
    https://docs.python.org/3/library/http.client.html#http.client.HTTPResponse.getheader

    :param str method: HTTP method to request (e.g. 'GET', 'POST')
    :param str url: URL to request
    :param unix_socket: path to Unix domain socket to query, or None for a normal TCP request
    :type unix_socket: str or None
    :param timeout: timeout in seconds, or None for no timeout (default: 15 seconds)
    :type timeout: float or None
    :param headers: HTTP headers as a mapping or list of key-value pairs
    :param params: parameters to be URL-encoded and added to the query string, as a mapping or list of key-value pairs
    :param body: payload body of the request
    :type body: bytes or None
    :param form: parameters to be form-encoded and sent as the payload body, as a mapping or list of key-value pairs
    :param json: object to be serialized as JSON and sent as the payload body
    :param bool verify: whether to verify TLS certificates (default: True)
    :param source_address: source address to bind to for TCP
    :type source_address: str or tuple(str, int) or None
    :param max_redirects: maximum number of redirects to follow, or None (the default) for no redirection
    :type max_redirects: int or None
    :param ssl_context: TLS config to control certificate validation, or None for default behavior
    :type ssl_context: ssl.SSLContext or None
    :return: http.client.HTTPResponse, yielded as context manager
    :rtype: http.client.HTTPResponse
    :raises: HTTPException
    """
    method = method.upper()
    headers = _prepare_outgoing_headers(headers)
    enc_params = _prepare_params(params)
    body = _prepare_body(body, form, json, headers)

    visited_urls: list[str] = []

    while max_redirects is None or len(visited_urls) <= max_redirects:
        url, conn, path = _prepare_request(
            method,
            url,
            enc_params=enc_params,
            timeout=timeout,
            unix_socket=unix_socket,
            verify=verify,
            source_address=source_address,
            ssl_context=ssl_context,
        )
        enc_params = ""  # don't reappend enc_params if we get redirected
        visited_urls.append(url)
        try:
            try:
                conn.request(method, path, headers=headers, body=body)
                response = conn.getresponse()
            except HTTPException:
                raise
            except IOError as e:
                # wrap any IOError that is not already an HTTPException
                # in HTTPException, exposing a uniform API for remote errors
                raise HTTPException(str(e)) from e
            redirect_url = _check_redirect(url, response.status, response.headers)
            if max_redirects is None or redirect_url is None:
                response.url = url  # https://bugs.python.org/issue42062
                yield response
                return
            else:
                url = redirect_url
                if response.status == 303:
                    # 303 See Other: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/303
                    method = "GET"
        finally:
            conn.close()

    raise TooManyRedirects(visited_urls)


class Response:
    """Response contains a completely consumed HTTP response.

    :ivar str url: the retrieved URL, indicating whether a redirection occurred
    :ivar int status_code: the HTTP status code
    :ivar http.client.HTTPMessage headers: the HTTP headers
    :ivar bytes body: the payload body of the response
    """

    __slots__ = ("url", "status_code", "headers", "body")

    def __init__(self, url, status_code, headers, body):
        self.url, self.status_code, self.headers, self.body = (
            url,
            status_code,
            headers,
            body,
        )

    def __repr__(self):
        return f"Response(status_code={self.status_code:d})"

    @property
    def ok(self):
        """ok returns whether the response had a successful status code
        (anything other than a 40x or 50x)."""
        return not (400 <= self.status_code < 600)

    @property
    def content(self):
        """content returns the response body (the `body` member). This is an
        alias for compatibility with requests.Response."""
        return self.body

    def raise_for_status(self) -> None:
        """raise_for_status checks the response's success code, raising an
        exception for error codes."""
        if not self.ok:
            raise HTTPErrorStatus(self.status_code)

    def json(self) -> dict:
        """Attempts to deserialize the response body as UTF-8 encoded JSON."""
        return loads(self.body)

    def _debugstr(self):
        buf = io.StringIO()
        print("HTTP", self.status_code, file=buf)
        for k, v in self.headers.items():
            print(f"{k}: {v}", file=buf)
        print(file=buf)
        try:
            print(self.body.decode("utf-8"), file=buf)
        except UnicodeDecodeError:
            print(f"<{len(self.body)} bytes binary data>", file=buf)
        return buf.getvalue()


class TooManyRedirects(HTTPException):
    """TooManyRedirects is raised when automatic following of redirects was
    enabled, but the server redirected too many times without completing."""

    pass


class HTTPErrorStatus(HTTPException):
    """HTTPErrorStatus is raised by Response.raise_for_status() to indicate an
    HTTP error code (a 40x or a 50x). Note that a well-formed response with an
    error code does not result in an exception unless raise_for_status() is
    called explicitly.
    """

    def __init__(self, status_code: int):
        self.status_code = status_code

    def __str__(self):
        return f"HTTP response returned error code {self.status_code:d}"


# end public API, begin internal implementation details

_JSON_CONTENTTYPE = "application/json"
_FORM_CONTENTTYPE = "application/x-www-form-urlencoded"


def _check_redirect(url, status, response_headers):
    """Return the URL to redirect to, or None for no redirection."""
    if status not in (301, 302, 303, 307, 308):
        return None
    location = response_headers.get("Location")
    if not location:
        return None
    parsed_location = urllib.parse.urlparse(location)
    if parsed_location.scheme:
        # absolute URL
        return location

    old_url = urllib.parse.urlparse(url)
    if location.startswith("/"):
        # absolute path on old hostname
        return urllib.parse.urlunparse(
            (
                old_url.scheme,
                old_url.netloc,
                parsed_location.path,
                parsed_location.params,
                parsed_location.query,
                parsed_location.fragment,
            )
        )

    # relative path on old hostname
    old_dir, _old_file = os.path.split(old_url.path)
    new_path = os.path.join(old_dir, location)
    return urllib.parse.urlunparse(
        (
            old_url.scheme,
            old_url.netloc,
            new_path,
            parsed_location.params,
            parsed_location.query,
            parsed_location.fragment,
        )
    )


def _prepare_outgoing_headers(headers):
    from pioreactor.config import config

    DEFAULT_AUTH = f'Basic {config.get("ui_basic_auth", "api_key", fallback="")}'

    if headers is None:
        headers = HTTPMessage()
    elif not isinstance(headers, HTTPMessage):
        new_headers = HTTPMessage()
        if hasattr(headers, "items"):
            iterator = headers.items()
        else:
            iterator = iter(headers)
        for k, v in iterator:
            new_headers[k] = v
        headers = new_headers
    _setdefault_header(headers, "User-Agent", DEFAULT_UA)
    _setdefault_header(headers, "Authorization", DEFAULT_AUTH)
    return headers


# XXX join multi-headers together so that get(), __getitem__(),
# etc. behave intuitively, then stuff them back in an HTTPMessage.
def _prepare_incoming_headers(headers):
    headers_dict = {}
    for k, v in headers.items():
        headers_dict.setdefault(k, []).append(v)
    result = HTTPMessage()
    # note that iterating over headers_dict preserves the original
    # insertion order in all versions since Python 3.6:
    for k, vlist in headers_dict.items():
        result[k] = ",".join(vlist)
    return result


def _setdefault_header(headers, name, value):
    if name not in headers:
        headers[name] = value


def _prepare_body(body, form, json, headers):
    if body is not None:
        if not isinstance(body, bytes):
            raise TypeError("body must be bytes or None", type(body))
        return body

    if json is not None:
        _setdefault_header(headers, "Content-Type", _JSON_CONTENTTYPE)
        return dumps(json)

    if form is not None:
        _setdefault_header(headers, "Content-Type", _FORM_CONTENTTYPE)
        return urllib.parse.urlencode(form, doseq=True)

    return None


def _prepare_params(params):
    if params is None:
        return ""
    return urllib.parse.urlencode(params, doseq=True)


def _prepare_request(
    method,
    url,
    *,
    enc_params="",
    timeout=DEFAULT_TIMEOUT,
    source_address=None,
    unix_socket=None,
    verify=True,
    ssl_context=None,
):
    import ssl

    """Parses the URL, returns the path and the right HTTPConnection subclass."""
    parsed_url = urllib.parse.urlparse(url)
    is_unix = unix_socket is not None
    scheme = parsed_url.scheme.lower()
    if scheme.endswith("+unix"):
        scheme = scheme[:-5]
        is_unix = True
        if scheme == "https":
            raise ValueError("https+unix is not implemented")

    if scheme not in ("http", "https"):
        raise ValueError("unrecognized scheme", scheme)

    is_https = scheme == "https"
    host = parsed_url.hostname
    port = 443 if is_https else 80
    if parsed_url.port:
        port = parsed_url.port

    if is_unix and unix_socket is None:
        unix_socket = urllib.parse.unquote(parsed_url.netloc)

    path = urllib.parse.quote(parsed_url.path)

    if parsed_url.query:
        if enc_params:
            path = f"{path}?{parsed_url.query}&{enc_params}"
        else:
            path = f"{path}?{parsed_url.query}"
    else:
        if enc_params:
            path = f"{path}?{enc_params}"
        else:
            pass  # just parsed_url.path in this case

    if isinstance(source_address, str):
        source_address = (source_address, 0)

    if is_unix:
        raise NotImplementedError("Need this? Get it from https://github.com/slingamn/mureq")
    elif is_https:
        if ssl_context is None:
            ssl_context = ssl.create_default_context()
            if not verify:
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
        conn = HTTPSConnection(
            host,
            port,
            source_address=source_address,
            timeout=timeout,
            context=ssl_context,
        )
    else:
        conn = HTTPConnection(host, port, source_address=source_address, timeout=timeout)

    munged_url = urllib.parse.urlunparse(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            path,
            parsed_url.params,
            "",
            parsed_url.fragment,
        )
    )
    return munged_url, conn, path
