
from keybert import KeyBERT


# Create the model only once
model = KeyBERT()


def extract_keywords(text):

    # Check if transcript is empty
    if not text or len(text.strip()) < 20:
        return []

    # Extract meaningful keywords / phrases
    keywords = model.extract_keywords(
        text,
        keyphrase_ngram_range=(1, 3),
        stop_words="english",
        use_mmr=True,
        diversity=0.5,
        top_n=10
    )

    keyword_list = []

    for word, score in keywords:

        # Ignore very weak keywords
        if score < 0.25:
            continue

        word = word.strip().lower()

        # Avoid duplicates
        if word not in keyword_list:
            keyword_list.append(word)

    return keyword_list

