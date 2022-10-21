#!/usr/bin/env python3

from pyserve import http

print(f"Hi! {http.GET['name']}")
