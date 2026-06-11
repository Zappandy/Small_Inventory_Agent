from datasets import load_dataset

HF_DATASETS = [
    {'repository':'Cognitive-Lab/NayanaOCR_Corpus_2025', 'lang': 'te'},
    'Reubencf/Adaption-low-resource-doc-qa',
    'AtharvImmverse/IndicVisionBench',
    
    ]

def main():
    for dataset in HF_DATASETS:
        print(f"Downloading {dataset}")
        ds = load_dataset(dataset['repository'], dataset['lang'] if 'lang' in dataset else None)
        ds.save_to_disk(f"data/{dataset}")

if __name__ == "__main__":
    main()