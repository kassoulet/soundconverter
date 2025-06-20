#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""utils used by tests"""

import sys
from importlib.machinery import SourceFileLoader
from importlib.util import spec_from_loader, module_from_spec
from soundconverter.util.settings import settings

from unittest.mock import patch

DEFAULT_SETTINGS = settings.copy()


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


def launch(argv=None, bin_path="bin/soundconverter"):
    """Start the soundconverter with the command line argument array argv.

    The batch mode is synchronous since it iterates the loop itself until
    finished.
    """
    # the tests should wait until the queues are done, so the sleep
    # can be omitted to speed them up.
    settings["gtk_close_sleep"] = 0

    if not argv:
        argv = []

    with patch.object(sys, "argv", [""] + [str(arg) for arg in argv]):
        loader = SourceFileLoader("launcher", bin_path)
        spec = spec_from_loader("launcher", loader)
        spec.loader.exec_module(module_from_spec(spec))
