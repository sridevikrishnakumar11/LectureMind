from sklearn.feature_extraction.text import TfidfVectorizer


def extract_keywords(text):
    if not text or len(text.strip()) < 20:
        return []

    # TF-IDF extracts words/phrases that are important
    # within the lecture transcript.
    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 3),
        max_features=50
    )

    try:
        matrix = vectorizer.fit_transform([text])
        scores = matrix.toarray()[0]
        words = vectorizer.get_feature_names_out()

        ranked = sorted(
            zip(words, scores),
            key=lambda x: x[1],
            reverse=True
        )

        keywords = []

        for word, score in ranked:
            if score <= 0:
                continue

            word = word.strip().lower()

            if word not in keywords:
                keywords.append(word)

            if len(keywords) == 10:
                break

        return keywords

    except Exception:
        return []