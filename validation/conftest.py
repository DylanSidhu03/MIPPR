"""Let validation tests import the pipeline (mippr) and the validation modules (ruler, legacy)."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "pipeline"))
sys.path.insert(0, str(HERE))
