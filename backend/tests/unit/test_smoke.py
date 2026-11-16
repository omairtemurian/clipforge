from clipforge import __version__


def test_version_is_non_empty() -> None:
    assert isinstance(__version__, str)
    assert __version__
