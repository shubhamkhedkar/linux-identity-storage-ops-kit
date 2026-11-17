import copy
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "spec" / "baseline.yaml"


@pytest.fixture
def raw():
    return copy.deepcopy(yaml.safe_load(SPEC.read_text()))
