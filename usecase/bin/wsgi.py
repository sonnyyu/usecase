#!/usr/bin/env python
#
"""energy saving wsgi module."""
import os
import sys

from usecase.api import api


current_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(current_dir)


def initialize_application():
    application = api.init([])
    return application
