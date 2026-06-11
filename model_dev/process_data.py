from pathlib import Path
from dataclasses import dataclass

DATA_DIR = Path("data")
PROCESSING_CONFIGS = {}

@dataclass
class DataProcessor:
    text_col: str
    image_col: str

    def process(self):
        raise NotImplementedError


def main():
    processed_datasets = []
    for dataset in DATA_DIR.iterdir():
        print(f"Processing {dataset}")
        processed_datasets.append(process_dataset(dataset))