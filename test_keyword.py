from models.keyword_extractor import extract_keywords


text = """
Artificial intelligence is a branch of computer science.
Machine learning allows computers to learn from data.
"""


result = extract_keywords(text)

print(result)