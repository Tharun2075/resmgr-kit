from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = sorted(ROOT.glob("examples/*/*.yaml"))


@pytest.fixture(params=EXAMPLES, ids=lambda p: p.stem)
def example(request):
    return request.param
