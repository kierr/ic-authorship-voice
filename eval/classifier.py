#!/usr/bin/env python3
"""eval/classifier.py — Five-Eyes register discriminator (§11.2).

The headline automated metric: fine-tuned model output must classify as uk_ic;
base-model, press, US and cousin-register (au/ca) output must not. Trained on
corpus/train.jsonl (positive → uk_ic) + corpus/contrast.jsonl (negative_us →
us, negative_press/contrast_misc → press, au_ic → au, ca_ic → ca,
negative_llm → llm) with TF-IDF bigrams + multinomial logistic regression.

Baseline (2026-08-19): weighted acc 0.97, uk_ic precision 1.00 — measured
in-sample on the then 3-way fold; the printed report is now cross-validated
so expect lower, honest numbers. The press class is thin (5 samples) and
minority-class recall is weak (ca/us/press often fold into uk_ic) — treat
uk_ic precision and overall accuracy as the reliable numbers, not per-class
recall, until the contrast classes grow.

Usage: .venv/bin/python eval/classifier.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "corpus")

# Explicit class → label map. Folding au_ic/ca_ic into uk_ic (the old
# fallthrough) trained cousin registers as the positive class and made the
# committed Five-Eyes discriminator 3-way.
LABELS = {
    "negative_us": "us",
    "negative_press": "press",
    "contrast_misc": "press",
    "ca_ic": "ca",
    "au_ic": "au",
    "negative_llm": "llm",
    # positive classes
    "confidence_statements": "uk_ic",
    "key_judgements": "uk_ic",
}


def load(path):
    out = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    return out


def label_of(r):
    # KeyError on unknown class: fail closed rather than train it as uk_ic
    return LABELS[r["class"]]


def build_pipeline():
    """Unfitted TF-IDF bigram + logistic-regression pipeline (the one config)."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    return make_pipeline(TfidfVectorizer(ngram_range=(1, 2), min_df=2),
                         LogisticRegression(max_iter=2000))


def train_classifier(X, y):
    """Fitted pipeline over raw texts X and labels y."""
    pipe = build_pipeline()
    pipe.fit(X, y)
    return pipe


def main():
    from sklearn.model_selection import cross_val_predict
    from sklearn.metrics import classification_report

    train = load(os.path.join(CORPUS, "train.jsonl"))
    contrast = load(os.path.join(CORPUS, "contrast.jsonl"))
    # negative_llm rows live in their own ledger (they are not a segment class
    # and never enter contrast.jsonl) — load them here or the declared 'llm'
    # label is unreachable dead vocabulary.
    import os.path as _p
    neg_llm_path = os.path.join(CORPUS, "negative_llm.jsonl")
    neg_llm = load(neg_llm_path) if _p.exists(neg_llm_path) else []

    X, y = [], []
    for s in train + contrast + neg_llm:
        X.append(s.get("text", ""))
        y.append(label_of(s))

    # cross_val_predict, not in-sample predict: scoring the training set gave
    # a vacuous "precision 1.00". Folds cap at the smallest class count —
    # StratifiedKFold raises outright when a class has fewer members than cv.
    from collections import Counter
    cv = min(5, min(Counter(y).values()))
    preds = cross_val_predict(build_pipeline(), X, y, cv=cv)
    acc = sum(p == t for p, t in zip(preds, y)) / len(y)
    print("%d-fold CV accuracy (%s): %.3f" % (cv, "/".join(sorted(set(y))), acc))
    print(classification_report(y, preds, zero_division=0))


if __name__ == "__main__":
    main()
