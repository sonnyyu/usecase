#!/usr/bin/env python
#
"""utility binary to manage database."""
from __future__ import print_function

import os
import os.path
import sys

from flask_script import Manager

from usecase.api import api
from usecase.db import database
from usecase.utils import logsetting


current_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(current_dir)
app_manager = Manager(api.app, usage="Perform operations")


@app_manager.command
def list_config():
    "List the commands."
    for key, value in api.app.config.items():
        print(key, value)


def main():
    logsetting.init()
    database.init()
    app_manager.run()


if __name__ == "__main__":
    main()
