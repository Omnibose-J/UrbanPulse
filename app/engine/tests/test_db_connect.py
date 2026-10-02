"""A failed connect must not repeat the URL."""

import pytest

from engine import db

PASSWORD = "h1a8-dummy-password"


def test_a_bad_url_does_not_leak_the_password(capsys):
    url = f"postgresql://urbanpulse:{PASSWORD}@[::1/none"
    with pytest.raises(Exception) as caught:
        db.connect(url)
    captured = capsys.readouterr()
    blob = f"{caught.value}\n{captured.out}\n{captured.err}"
    if PASSWORD in blob:
        raise AssertionError("password appeared in the connect error")
    assert str(caught.value) == "database connection failed"
    assert caught.value.__cause__ is None
