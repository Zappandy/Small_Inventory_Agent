from pathlib import Path
import os


APP_NAME = "Dukaan Saathi"
DB_PATH = os.getenv("DB_PATH", "data/dukaan.db")
DATA_DIR = Path("data")
SAMPLES_DIR = Path("samples")