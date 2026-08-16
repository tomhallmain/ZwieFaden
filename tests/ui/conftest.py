"""
conftest for tests/ui/.

Mirrors the module-level env var bootstrap from the root conftest.py. This is
necessary because pytest loads each directory's conftest before collecting
tests in that directory, and the singletons may not yet be imported when the
root conftest runs in some collection orders.
"""

import os

# Re-apply the env vars at module load. setdefault means the root conftest's
# values win if already set; this just ensures they're present either way.
if "ZWIEFADEN_CACHE_DIR" not in os.environ:
    import atexit
    import shutil
    import tempfile

    _tmp = tempfile.mkdtemp(prefix="zwiefaden_ui_")
    os.environ["ZWIEFADEN_CACHE_DIR"] = os.path.join(_tmp, "cache")
    os.environ["ZWIEFADEN_LOG_DIR"] = os.path.join(_tmp, "logs")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.makedirs(os.environ["ZWIEFADEN_CACHE_DIR"], exist_ok=True)
    os.makedirs(os.environ["ZWIEFADEN_LOG_DIR"], exist_ok=True)
    atexit.register(shutil.rmtree, _tmp, True)
