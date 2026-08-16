"""
Root conftest for the ZwieFaden test suite.

IMPORTANT: The env vars below must be set at module load time -- before any
app module is imported -- because `utils/app_info_cache.py` instantiates its
`app_info_cache` singleton at import time, and `utils/logging_setup.py`
writes a real log file the first time `get_logger()` is called for a given
logger name (which several modules do at their own module level, e.g.
`extensions/llm.py`, `app.py`). Any nested conftest.py must mirror this same
module-level bootstrap for the same reason -- pytest loads each directory's
conftest before collecting tests in that directory, and the singletons may
not yet be imported when this root conftest runs in some collection orders.
"""

import atexit
import os
import shutil
import sys
import tempfile

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Bootstrap a safe temporary location so that the singletons created during
# initial import never touch the real project-root app_info_cache.enc or the
# real ~/.local/share/ZwieFaden/logs (or %APPDATA%\ZwieFaden\logs) directory.
_bootstrap_tmp = tempfile.mkdtemp(prefix="zwiefaden_tests_")
os.environ.setdefault("ZWIEFADEN_CACHE_DIR", os.path.join(_bootstrap_tmp, "cache"))
os.environ.setdefault("ZWIEFADEN_LOG_DIR", os.path.join(_bootstrap_tmp, "logs"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.makedirs(os.environ["ZWIEFADEN_CACHE_DIR"], exist_ok=True)
os.makedirs(os.environ["ZWIEFADEN_LOG_DIR"], exist_ok=True)
atexit.register(shutil.rmtree, _bootstrap_tmp, True)

import pytest


class _FakeKeyring:
    """In-memory stand-in for the OS keyring, so tests never touch the real
    Windows Credential Manager / macOS Keychain / Linux Secret Service --
    utils/encryptor.py (used by AppInfoCache to encrypt its cache file) goes
    through `keyring` for every key it stores or reads."""

    def __init__(self):
        self._store = {}

    def get_password(self, service_name, key):
        return self._store.get((service_name, key))

    def set_password(self, service_name, key, value):
        self._store[(service_name, key)] = value

    def delete_password(self, service_name, key):
        if (service_name, key) not in self._store:
            raise Exception("Password not found")
        del self._store[(service_name, key)]


def repoint_singleton_bindings(monkeypatch, attr_name, old_obj, new_obj):
    """Repoint every imported module's module-level binding of *old_obj* to
    *new_obj* (undone automatically by monkeypatch at test teardown).

    Modules that do e.g. `from utils.app_info_cache import app_info_cache` at
    module level hold their own reference to the singleton, so patching only
    the source module leaves those bindings stale. Sweeping sys.modules
    retires that whack-a-mole: the identity comparison guarantees only
    bindings to the exact old object are touched.
    """
    for module in list(sys.modules.values()):
        try:
            if getattr(module, attr_name, None) is old_obj:
                monkeypatch.setattr(module, attr_name, new_obj)
        except Exception:
            continue


@pytest.fixture(autouse=True)
def fake_keyring(monkeypatch):
    """Replace the OS keyring backend with an in-memory fake for every test."""
    import keyring

    fake = _FakeKeyring()
    monkeypatch.setattr(keyring, "get_password", fake.get_password)
    monkeypatch.setattr(keyring, "set_password", fake.set_password)
    monkeypatch.setattr(keyring, "delete_password", fake.delete_password)
    yield fake


@pytest.fixture(autouse=True)
def isolated_singletons(tmp_path, monkeypatch):
    """Re-initialise the app_info_cache singleton for each test, pointing at
    a fresh per-test temp directory. No production files are touched.

    (The log directory is only bootstrapped once, at collection time above --
    utils/logging_setup.get_logger() caches loggers by name and skips its
    directory setup on every call after the first, so a per-test override
    here would have no effect on already-created loggers.)
    """
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    monkeypatch.setenv("ZWIEFADEN_CACHE_DIR", str(cache_dir))

    import utils.app_info_cache as aic

    old_cache = aic.app_info_cache
    new_cache = aic.AppInfoCache()
    repoint_singleton_bindings(monkeypatch, "app_info_cache", old_cache, new_cache)

    yield new_cache


@pytest.fixture(autouse=True)
def isolated_join_store(tmp_path, monkeypatch):
    """Point JoinMulti's pickle store / analysis-output locations at a
    per-test temp directory so tests never touch configs/join_multi_store*.pkl
    or configs/join_multi_analysis.txt."""
    from join.join import JoinMulti

    monkeypatch.setattr(JoinMulti, "STORE_LOCATION", str(tmp_path / "join_multi_store.pkl"))
    monkeypatch.setattr(JoinMulti, "ANALYSIS_LOCATION", str(tmp_path / "join_multi_analysis.txt"))


@pytest.fixture(autouse=True)
def no_blocking_dialogs(monkeypatch):
    """Prevent any QMessageBox/QFileDialog call from opening a real modal
    event loop -- there's no user present in a headless/offscreen test run
    to dismiss one, so an un-mocked dialog would hang the test instead of
    failing it. Tests that care about a specific dialog answer (e.g. the
    "No" branch of a confirmation) can override these locally with their own
    monkeypatch call."""
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", "")))
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", staticmethod(lambda *a, **k: ([], "")))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))


@pytest.fixture(autouse=True)
def block_real_llm_network_calls(monkeypatch):
    """Fail fast (instead of hanging or depending on a real Ollama server)
    if a test exercises extensions.llm.LLM without mocking its response.
    Tests that intentionally exercise the LLM call path must monkeypatch
    LLM.generate_response (or urlopen) themselves."""
    from urllib import request as urllib_request

    def _blocked(*args, **kwargs):
        raise AssertionError(
            "Test attempted a real network call via urllib.request.urlopen. "
            "Mock extensions.llm.LLM.generate_response instead of relying on "
            "network access."
        )

    monkeypatch.setattr(urllib_request, "urlopen", _blocked)
