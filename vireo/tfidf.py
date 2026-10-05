"""Stage 2 of the categoriser: character n-gram TF-IDF + logistic regression, trained on the
messages the rules labelled confidently (weak supervision), applied only where the rules were unsure.
Character n-grams tolerate typos and Hinglish spellings that word rules miss."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

MIN_PER_CLASS = 5
TRAIN_CONF = 0.8


def fit_predict(text: pd.Series, rule_cat: pd.Series, rule_conf: pd.Series, apply_mask: pd.Series):
    """Train on rows with rule confidence >= TRAIN_CONF; predict rows in apply_mask.
    Returns (labels, probabilities) for the apply_mask rows; empty if too little training data."""
    train = (rule_conf >= TRAIN_CONF) & rule_cat.ne("unclear")
    counts = rule_cat[train].value_counts()
    keep = counts[counts >= MIN_PER_CLASS].index
    train &= rule_cat.isin(keep)
    if len(keep) < 2 or not apply_mask.any():
        return pd.Series(dtype=object), pd.Series(dtype=float)
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True)
    X = vec.fit_transform(text[train])
    clf = LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced", random_state=0)
    clf.fit(X, rule_cat[train])
    P = clf.predict_proba(vec.transform(text[apply_mask]))
    idx = text[apply_mask].index
    return (pd.Series(clf.classes_[P.argmax(1)], index=idx),
            pd.Series(P.max(1), index=idx).astype(float))
