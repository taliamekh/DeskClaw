#!/usr/bin/env python3
"""Simple checker for the vision HTTP API endpoints."""

import json
import urllib.request

BASE_URL = "http://127.0.0.1:8787"
ENDPOINTS = ["/objects", "/robot", "/path"]


def fetch(path):
    with urllib.request.urlopen(BASE_URL + path, timeout=2.0) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def main():
    for endpoint in ENDPOINTS:
        payload = fetch(endpoint)
        print(f"{endpoint}: {payload.get('type', 'unknown')}")
        print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

