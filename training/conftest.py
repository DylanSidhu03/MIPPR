"""Let training tests import the training modules (and, through common.py, the pipeline)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
