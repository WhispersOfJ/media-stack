#!/usr/bin/env python3
"""Healthcheck for Docker — hits Django's /healthz endpoint."""
import sys
import urllib.request

try:
    resp = urllib.request.urlopen("http://localhost:8420/healthz", timeout=5)
    sys.exit(0 if resp.status == 200 else 1)
except Exception:
    sys.exit(1)
