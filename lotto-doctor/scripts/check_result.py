#!/usr/bin/env python3
"""Thin wrapper: check and send result."""
from lotto_doctor.cli import main

if __name__ == "__main__":
    main(["check-result", "--send"])
