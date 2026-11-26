from pathlib import Path

import pytest

from delinquance.scrub import clean, load_raw

# Extract of the real departmental base (8 departments, all indicators, 2016-2025).
SAMPLE = Path(__file__).parent / "data" / "sample.csv"


@pytest.fixture(scope="session")
def raw():
    return load_raw(SAMPLE)


@pytest.fixture(scope="session")
def cleaned(raw):
    return clean(raw)
