import copy
import json
from pathlib import Path

import pytest

from tinyspice.schemas import load_device_limits

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def base_spec_dict():
    return json.loads((ROOT / "configs/experiments/example_idvg.json").read_text())


@pytest.fixture
def spec_dict(base_spec_dict):
    return copy.deepcopy(base_spec_dict)


@pytest.fixture
def limits():
    return load_device_limits(ROOT / "configs/devices/sky130_nfet_01v8.json")
