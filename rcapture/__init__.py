import json
import warnings
from functools import partial
from textwrap import dedent, indent
from typing import Optional, Callable, List
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qsl

import requests
from requests.utils import default_headers
from requests import Request, Response, PreparedRequest
from responses import matchers


def erase_default_header_items(headers):
    new_headers = headers.copy()
    requests_default_headers = default_headers()
    for key, value in requests_default_headers.items():
        if key in new_headers and new_headers[key] == value:
            del new_headers[key]
    return new_headers


def render_matchers(matchers):
    rendered_matchers = ""
    for matcher in matchers:
        args = [repr(x) for x in matcher.args]
        args.extend(f"{k}={v!r}" for (k, v) in matcher.keywords.items())
        rendered_args = ", ".join(args)
        rendered_matchers += f"matchers.{matcher.func.__name__}({rendered_args}),\n"
    return rendered_matchers.rstrip("\n")


class CapturedRequestResponse(object):
    def __init__(
        self,
        request: PreparedRequest,
        extra_kwargs: dict,
        response: Response,
        exc: Optional[Exception] = None,
    ):
        """Represents captured Request - Response pair.
        :param request: PreparedRequest object.
        :param extra_kwargs: extra kwargs passed to Session.send. (Includes environment configuration)
        :param response: Captured Response object. None if request resulted in exception.
        :param exc: Captured exception, if any.
        """
        self.request = request
        self.extra_kwargs = extra_kwargs
        self.response = response
        self.exc = exc

    def _render_prep(
        self,
        match_body=True,
        match_query_param=True,
        match_header=True,
        match_request_kwargs=False,
        include_response_date=False,
    ):
        split = urlsplit(self.request.url)
        request_url_base = f"{split.scheme}://{split.netloc}{split.path}"
        request_url_query = split.query

        # Prepare Response object constructor arguments
        response_build_args = {
            "method": self.request.method,
            "url": request_url_base,
        }
        if self.exc:
            response_build_args.update(
                {
                    "body": self.exc,
                }
            )
        else:
            if not include_response_date:
                self.response.headers.pop("Date", None)
            response_build_args.update(
                {
                    "status": self.response.status_code,
                    "headers": self.response.headers,
                }
            )
            try:
                json_response_body = self.response.json()
                response_build_args.update({"json": json_response_body})
            except json.JSONDecodeError:
                response_build_args.update({"body": self.response.content})

        # Prepare request matcher
        request_matcher = []
        request_content_type = self.request.headers.get("content-type")

        if match_body and request_content_type is not None:
            request_content_type = request_content_type.lower()
            if request_content_type == "application/x-www-form-urlencoded":
                request_matcher.append(
                    partial(
                        matchers.urlencoded_params_matcher,
                        dict(parse_qsl(self.request.body)),
                    )
                )
            elif request_content_type == "application/json":
                request_matcher.append(
                    partial(matchers.json_params_matcher, json.loads(self.request.body))
                )
            else:
                warnings.warn(
                    f"Unsupported Content-Type for request body matching: {request_content_type}."
                )

        if match_query_param and request_url_query:
            parsed_query = dict(parse_qsl(request_url_query))
            request_matcher.append(partial(matchers.query_param_matcher, parsed_query))

        if match_header:
            stripped_headers = erase_default_header_items(self.request.headers)
            if stripped_headers:
                request_matcher.append(
                    partial(
                        matchers.header_matcher,
                        stripped_headers,
                    )
                )

        if match_request_kwargs:
            request_matcher.append(
                partial(matchers.request_kwargs_matcher, self.extra_kwargs)
            )

        return response_build_args, request_matcher

    def render(self, **kwargs):
        response_build_args, request_matcher = self._render_prep(**kwargs)

        rendered_args = ""
        for kw, value in response_build_args.items():

            rendered_args += f"{kw}={value!r},\n"
        rendered_args = rendered_args.rstrip("\n")
        rendered_args = indent(rendered_args, " " * 16)

        rendered_matchers = render_matchers(request_matcher).rstrip("\n")
        rendered_matchers = indent(rendered_matchers, " " * 16)

        representation = dedent(
            f"""
        responses.add(
            responses.Response(
{rendered_args}
            ),
            match=[
{rendered_matchers}
            ],
        )"""
        )
        return representation


class Capturer(object):
    def __init__(self):
        self._patcher = None
        self._unwrapped_send = None
        self._request_history = []

    def start(self):
        self._unwrapped_send = requests.Session.send

        def unbound_send_wrapper(session, request, **kwargs):
            response, captured_exc = None, None
            try:
                response = self._unwrapped_send(session, request, **kwargs)
                return response
            except Exception as e:
                captured_exc = e
                raise
            finally:
                self._request_history.append(
                    CapturedRequestResponse(request, kwargs, response, captured_exc)
                )

        self._patcher = patch("requests.Session.send", unbound_send_wrapper)
        self._patcher.start()

    def stop(self):
        if self._patcher:
            self._patcher.stop()

    def dump(self) -> List[CapturedRequestResponse]:
        return self._request_history
