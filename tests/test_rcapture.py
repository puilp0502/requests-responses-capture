import requests
from requests.structures import CaseInsensitiveDict

from rcapture import erase_default_header_items, Capturer


def test_erase_default_header_items():
    headers_to_test = CaseInsensitiveDict(
        {
            "User-Agent": f"python-requests/{requests.__version__}",
            "Accept-Encoding": "gzip, deflate",
            "Accept": "*/*",
            "Connection": "keep-alive",
            "Authorization": "Bearer 123",
        }
    )

    stripped_header = erase_default_header_items(headers_to_test)
    assert dict(stripped_header) == {"Authorization": "Bearer 123"}


def test_request_resp_repr_get(capturer, context):
    requests.get("http://httpbin.org/get")
    repr = capturer.dump()[0].render()
    eval(repr, context)


def test_request_resp_repr_multiple_requests(capturer: Capturer, context):
    requests.get("http://httpbin.org/get")
    requests.post("http://httpbin.org/post")
    dumps = capturer.dump()

    assert dumps[0].request.method == "GET"
    repr = dumps[0].render()
    print(repr)
    eval(repr, context)

    assert dumps[1].request.method == "POST"
    repr = dumps[1].render()
    print(repr)
    eval(repr, context)


def test_request_resp_repr_post_json(capturer, context):
    requests.post("http://httpbin.org/post", json={"Hello": "World"})
    print()
    repr = capturer.dump()[0].render()
    eval(repr, context)


def test_request_resp_repr_post_urlencoded(capturer, context):
    requests.post("http://httpbin.org/post", data={"Hello": "World"})
    repr = capturer.dump()[0].render()
    print(repr)
    eval(repr, context)
