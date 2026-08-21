import os

# core.arr_client reads these via bare os.environ[...] at import time (mirrors
# the FastAPI-era app.py: a missing key is a deployment misconfiguration that
# should fail loudly in production). Tests need *some* value present so the
# module is importable; set defaults here, before any test module imports
# core.arr_client, without clobbering a real value if one is already set.
os.environ.setdefault("RADARR_API_KEY", "test-radarr-key")
os.environ.setdefault("SONARR_API_KEY", "test-sonarr-key")
