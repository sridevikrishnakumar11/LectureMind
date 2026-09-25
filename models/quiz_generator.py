"""Deterministic, transcript-grounded multiple choice quiz generation."""

import random
import re
from collections import Counter


def _sentences(transcript):
    sentences = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", transcript or ""):
        sentence = sentence.strip()
        # Whisper output may be a single long sentence. Keep it usable by making
        # overlapping, transcript-verbatim chunks rather than rejecting it.
        if len(sentence) > 380:
            words = sentence.split()
            sentences.extend(" ".join(words[index:index + 45]) for index in range(0, len(words), 35))
        else:
            sentences.append(sentence)
    return [sentence for sentence in sentences if 15 <= len(sentence) <= 380]


def _normalise_concepts(keywords):
    seen = set()
    concepts = []
    for value in keywords or []:
        value = str(value).strip()
        key = value.lower()
        if value and key not in seen and len(value) > 1:
            seen.add(key)
            concepts.append(value)
    return concepts


def _transcript_terms(transcript, existing):
    """Supply grounded fallback concepts when KeyBERT returned too few matches."""
    stop_words = {"about", "after", "again", "being", "because", "between", "could", "data", "from", "have", "into", "kind", "like", "more", "other", "really", "that", "their", "these", "this", "together", "used", "ways", "what", "when", "with", "would", "your"}
    words = re.findall(r"[A-Za-z][A-Za-z-]{3,}", transcript or "")
    counts = Counter(word.lower() for word in words if word.lower() not in stop_words)
    known = {item.lower() for item in existing}
    return [word for word, _ in counts.most_common() if word not in known][:12]


def _normalise_words(text):
    words = re.findall(r"[a-z0-9]+", str(text).casefold())
    normalised = []
    for word in words:
        if len(word) > 3 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        normalised.append(word)
    return normalised


def _concept_match_score(sentence, concept):
    concept_words = _normalise_words(concept)
    sentence_words = _normalise_words(sentence)
    if not concept_words:
        return 0
    for index in range(len(sentence_words) - len(concept_words) + 1):
        if sentence_words[index:index + len(concept_words)] == concept_words:
            return 100
    matched = len(set(concept_words) & set(sentence_words))
    if matched < max(1, (len(concept_words) + 1) // 2):
        return 0
    return round(matched * 60 / len(concept_words))


def _mask_concept(sentence, concept):
    masked = sentence
    for word in set(re.findall(r"[A-Za-z0-9]+", concept)):
        stem = word[:-1] if len(word) > 3 and word.endswith("s") else word
        masked = re.sub(r"\b" + re.escape(stem) + r"s?\b", "_____", masked, flags=re.IGNORECASE)
    return masked


def _build_options(correct, concepts, fallback_concepts):
    correct_words = set(_normalise_words(correct))
    options = [correct]
    seen = {correct.casefold()}
    candidates = concepts + fallback_concepts
    for candidate in candidates:
        key = candidate.casefold()
        candidate_words = set(_normalise_words(candidate))
        if key in seen or not candidate_words:
            continue
        if candidate_words <= correct_words or correct_words <= candidate_words:
            continue
        options.append(candidate)
        seen.add(key)
        if len(options) == 4:
            return options
    for candidate in candidates:
        key = candidate.casefold()
        if key not in seen:
            options.append(candidate)
            seen.add(key)
        if len(options) == 4:
            return options
    return options


def generate_quiz(transcript, keywords, question_count=5):
    """Create cloze MCQs whose answer and explanation are exact lecture text.

    Distractors are other extracted lecture concepts, avoiding unsupported general
    knowledge choices. Raises ValueError when the source is too thin for a quiz.
    """
    concepts = _normalise_concepts(keywords)
    fallback_concepts = _transcript_terms(transcript, concepts)
    sentences = _sentences(transcript)
    if not sentences:
        raise ValueError("This lecture needs more transcribed content before a quiz can be generated.")

    candidates = []
    for concept in concepts + fallback_concepts:
        matches = [( _concept_match_score(sentence, concept), index, sentence)
                   for index, sentence in enumerate(sentences)]
        matches = [match for match in matches if match[0]]
        if matches:
            score, _, sentence = max(matches, key=lambda match: (match[0], -match[1]))
            candidates.append((score, sentence, concept))
        if len(candidates) >= min(10, question_count):
            break

    questions = []
    used_concepts = set()
    for _, sentence, correct in candidates:
        if correct.lower() in used_concepts:
            continue
        options = _build_options(correct, concepts, fallback_concepts)
        if len(options) < 4:
            continue
        masked = _mask_concept(sentence, correct)
        random.Random(f"{sentence}:{correct}").shuffle(options)
        mode = len(questions) % 3
        if mode == 0:
            prompt = "A learner encounters the situation described in this passage. Which lecture concept would guide the response?"
            level = "application"
        elif mode == 1:
            prompt = "The passage describes a relationship between ideas. Which concept best completes that comparison?"
            level = "comparison"
        else:
            prompt = "Based on the cause and result described in this passage, which concept best explains the outcome?"
            level = "reasoning"
        questions.append({
            "id": f"q{len(questions) + 1}",
            "question": f"{prompt} \u201c{masked}\u201d",
            "options": options,
            "correct_answer": correct,
            "explanation": sentence,
            "concept": correct,
            "level": level,
            "generation_version": 4,
        })
        used_concepts.add(correct.lower())
        if len(questions) >= min(10, question_count):
            break

    if len(questions) < 5:
        raise ValueError("This lecture does not yet contain enough distinct, supported concepts for a five-question quiz.")
    return questions


def generate_targeted_quiz(transcript, concept, keywords, previous_questions=None, question_count=3):
    """Create new transcript-grounded questions focused on one weak concept."""
    target = str(concept or "").strip()
    if not target:
        raise ValueError("A revision concept is required.")

    concepts = _normalise_concepts(keywords)
    fallback_concepts = _transcript_terms(transcript, concepts)
    sentences = _sentences(transcript)
    previous = {
        (str(item.get("explanation") or "").strip().casefold(),
         str(item.get("correct_answer") or "").strip().casefold())
        for item in previous_questions or []
    }
    candidates = []
    for index, sentence in enumerate(sentences):
        score = _concept_match_score(sentence, target)
        if score and (sentence.casefold(), target.casefold()) not in previous:
            candidates.append((score, index, sentence))
    candidates.sort(key=lambda item: (-item[0], item[1]))

    questions = []
    used_sentences = set()
    for _, index, sentence in candidates:
        if index in used_sentences:
            continue
        options = _build_options(target, concepts, fallback_concepts)
        if len(options) < 4:
            continue
        random.Random(f"revision:{sentence}:{target}").shuffle(options)
        mode = len(questions) % 3
        if mode == 0:
            prompt = "A learner faces the situation described in this lecture passage. Which weak concept should they revisit?"
            level = "application"
        elif mode == 1:
            prompt = "Which concept best accounts for the relationship described in this lecture passage?"
            level = "comparison"
        else:
            prompt = "Which concept best explains the result described in this lecture passage?"
            level = "reasoning"
        questions.append({
            "id": f"q{len(questions) + 1}",
            "question": f"{prompt} \u201c{sentence}\u201d",
            "options": options,
            "correct_answer": target,
            "explanation": sentence,
            "concept": target,
            "level": level,
            "generation_version": 5,
            "practice_for": target,
        })
        used_sentences.add(index)
        if len(questions) >= min(3, question_count):
            break

    if len(questions) < 2:
        raise ValueError("This lecture does not contain enough new transcript material for targeted practice.")
    return questions
