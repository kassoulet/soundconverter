#!/usr/bin/python3

"""utils used by tests"""

import sys
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from unittest.mock import patch
import os

from soundconverter.util.settings import settings

DEFAULT_SETTINGS = settings.copy()
BUILD_DIR = "builddir"


def reset_settings():
    """Reset the global settings to their initial state."""
    # convert to list otherwise del won't work
    for key in list(settings.keys()):
        if key in DEFAULT_SETTINGS:
            settings[key] = DEFAULT_SETTINGS[key]
        else:
            del settings[key]
    # batch tests assume that recursive is off by default:
    assert ("recursive" not in settings) or (not settings["recursive"])


def launch(argv=None, bin_path="soundconverter"):
    """Start the soundconverter with the command line argument array argv.

    The batch mode is synchronous since it iterates the loop itself until
    finished.
    """
    # the tests should wait until the queues are done, so the sleep
    # can be omitted to speed them up.
    settings["gtk_close_sleep"] = 0

    if not argv:
        argv = []

    # Use the build directory specified in the environment or default to 'builddir'
    build_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), BUILD_DIR)
    with patch.object(sys, "argv", [""] + [str(arg) for arg in argv]):
        loader = SourceFileLoader("launcher", os.path.join(build_dir, bin_path))
        spec = spec_from_loader("launcher", loader)
        spec.loader.exec_module(module_from_spec(spec))
