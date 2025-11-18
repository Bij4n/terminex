#!/usr/bin/env python3
"""Legacy entry point — delegates to terminex.app."""

from __future__ import annotations

import sys

from terminex.app import main

if __name__ == "__main__":
    sys.exit(main())
