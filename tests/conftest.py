import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def northwind():
    """A fresh copy of the demo graph in its own tenant, deleted afterwards."""
    from data.generate import build
    from data.load import load
    from retract.db import graph

    load(build(), tenant="test_northwind")
    g = graph("test_northwind")
    yield g
    g.delete()
