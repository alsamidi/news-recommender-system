"""
Indonesian Text Preprocessing Pipeline
Sastrawi-based: tokenize, stem, stopword removal, alay normalization
"""
import re
import pandas as pd
from pathlib import Path
from typing import List, Optional
from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
from Sastrawi.StopWordRemover.StopWordRemoverFactory import StopWordRemoverFactory


class IndonesianPreprocessor:
    def __init__(
        self,
        stopwords_path: Optional[str] = None,
        alay_dict_path: Optional[str] = None,
        min_token_len: int = 2,
        max_token_len: int = 50,
        remove_numbers: bool = True,
        remove_punct: bool = True,
    ):
        self.stemmer = StemmerFactory().create_stemmer()
        self.stopword_remover = StopWordRemoverFactory().create_stop_word_remover()
        self.custom_stopwords = self._load_stopwords(stopwords_path)
        self.alay_dict = self._load_alay_dict(alay_dict_path)
        self.min_token_len = min_token_len
        self.max_token_len = max_token_len
        self.remove_numbers = remove_numbers
        self.remove_punct = remove_punct

    def _load_stopwords(self, path: Optional[str]) -> set:
        if path and Path(path).exists():
            with open(path, "r", encoding="utf-8") as f:
                return set(line.strip() for line in f if line.strip())
        return set()

    def _load_alay_dict(self, path: Optional[str]) -> dict:
        if path and Path(path).exists():
            df = pd.read_csv(path)
            return dict(zip(df["alay"], df["baku"]))
        return {}

    def normalize_alay(self, text: str) -> str:
        if not self.alay_dict:
            return text
        words = text.split()
        return " ".join(self.alay_dict.get(w, w) for w in words)

    def clean_text(self, text: str) -> str:
        if not isinstance(text, str):
            return ""
        # Lowercase
        text = text.lower()
        # Normalize alay
        text = self.normalize_alay(text)
        # Remove URLs
        text = re.sub(r"http\S+|www\S+|https\S+", "", text)
        # Remove mentions/hashtags
        text = re.sub(r"@\w+|#\w+", "", text)
        # Remove numbers
        if self.remove_numbers:
            text = re.sub(r"\d+", "", text)
        # Remove punctuation
        if self.remove_punct:
            text = re.sub(r"[^\w\s]", " ", text)
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def tokenize(self, text: str) -> List[str]:
        # Simple whitespace tokenizer (Sastrawi works on full text)
        return text.split()

    def stem(self, text: str) -> str:
        return self.stemmer.stem(text)

    def remove_stopwords(self, text: str) -> str:
        # Sastrawi stopword remover
        text = self.stopword_remover.remove(text)
        # Custom stopwords
        words = text.split()
        words = [w for w in words if w not in self.custom_stopwords]
        return " ".join(words)

    def filter_tokens(self, tokens: List[str]) -> List[str]:
        return [
            t for t in tokens
            if self.min_token_len <= len(t) <= self.max_token_len
        ]

    def process(self, text: str) -> str:
        """Full pipeline: clean -> stem -> stopword -> tokenize -> filter"""
        text = self.clean_text(text)
        text = self.stem(text)
        text = self.remove_stopwords(text)
        tokens = self.tokenize(text)
        tokens = self.filter_tokens(tokens)
        return " ".join(tokens)

    def process_batch(self, texts: List[str]) -> List[str]:
        return [self.process(t) for t in texts]


def load_config(config_path: str) -> dict:
    import yaml
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/preprocessing.yaml")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    cfg = load_config(args.config)

    preprocessor = IndonesianPreprocessor(
        stopwords_path=cfg.get("stopwords_path"),
        alay_dict_path=cfg.get("alay_dict_path"),
        min_token_len=cfg.get("min_token_length", 2),
        max_token_len=cfg.get("max_token_length", 50),
        remove_numbers=cfg.get("remove_numbers", True),
        remove_punct=cfg.get("remove_punctuation", True),
    )

    # Load data
    df = pd.read_parquet(args.input) if args.input.endswith(".parquet") else pd.read_csv(args.input)

    text_col = cfg.get("text_column", "content")
    df["processed_text"] = preprocessor.process_batch(df[text_col].astype(str).tolist())

    # Save
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.output, index=False)
    print(f"Processed {len(df)} articles -> {args.output}")


if __name__ == "__main__":
    main()