"""Retrieval-only question answering for a single lecture transcript."""

import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


NOT_FOUND_MESSAGE = "This information was not found in the lecture."


def _sentences(transcript):
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", transcript or "")
        if len(sentence.strip()) >= 25
    ]


def answer_question(transcript, question):
    """Return only high-confidence transcript context; never invent an answer."""
    question = (question or "").strip()
    sentences = _sentences(transcript)
    if not question or not sentences:
        return {"answer": NOT_FOUND_MESSAGE, "context": []}

    try:
        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        matrix = vectorizer.fit_transform(sentences + [question])
        scores = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
    except ValueError:
        return {"answer": NOT_FOUND_MESSAGE, "context": []}

    ranked = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
    best_score = scores[ranked[0]] if ranked else 0
    if best_score < 0.08:
        return {"answer": NOT_FOUND_MESSAGE, "context": []}

    selected = [sentences[index] for index in ranked[:2] if scores[index] >= 0.05]
    return {
        "answer": " ".join(selected),
        "context": selected,
    }
