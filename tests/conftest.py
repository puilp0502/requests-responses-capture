import pytest
import responses
from responses import matchers

from rcapture import Capturer


@pytest.fixture
def capturer():
    c = Capturer()
    c.start()
    yield c
    c.stop()


@pytest.fixture
def context():
    return {"responses": responses, "matchers": matchers}
