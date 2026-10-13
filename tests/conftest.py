import sys
from pathlib import Path

# aby šlo `pytest` pouštět z kořene repozitáře bez instalace balíčku
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
