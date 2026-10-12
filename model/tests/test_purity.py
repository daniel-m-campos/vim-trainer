"""The model must not read the clock or global randomness (time and seeds are arguments)."""

from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "vimtrainer_model"
APP_MODEL = Path(__file__).resolve().parent.parent.parent / "app" / "src" / "model" / "model.ts"


def test_python_model_has_no_clock_or_random():
    for path in PACKAGE.glob("*.py"):
        text = path.read_text()
        assert "import random" not in text and "import time" not in text and "datetime" not in text, path.name


def test_ts_model_has_no_clock_or_random():
    text = APP_MODEL.read_text()
    assert "Date.now" not in text and "Math.random" not in text and "performance.now" not in text
