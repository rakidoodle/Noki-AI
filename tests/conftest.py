import pytest


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", default=False,
                     help="Run tests that make live OpenRouter requests")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        return
    skip_live = pytest.mark.skip(reason="use --live to run an OpenRouter request")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
