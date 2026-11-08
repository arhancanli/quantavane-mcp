"""Shared fixtures. Checks run one at a time; each checker is a separate process under the sandbox's limits."""
import pytest

from quantavane_mcp.checking import Checker
from quantavane_mcp.config import Settings
from quantavane_mcp.data import Benchmark, Store


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
def cache_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("cache")


@pytest.fixture(scope="session")
def store():
    return Store(benchmark=Benchmark())


@pytest.fixture
def settings(tmp_path, cache_dir):
    return Settings(roots=(tmp_path.resolve(),), cache_dir=cache_dir, timeout_s=300, max_timeout_s=900,
                    memory_mb=1024)


@pytest.fixture
def checker(store, settings):
    return Checker(store, settings)
