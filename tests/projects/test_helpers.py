import pytest

from projects.helpers import lowercase_first_char


@pytest.mark.parametrize(
    "string, expected",
    [
        ("Manage members", "manage members"),
        ("Manage API keys", "manage API keys"),
        ("", ""),
    ],
)
def test_lowercase_first_char(string, expected):
    assert lowercase_first_char(string) == expected
