"""Build browser-ready mind map data from actual lecture content."""

import re


_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "is", "it", "of", "on", "or", "the", "to", "was", "with",
}
_FALLBACK_DESCRIPTION = "No explanatory sentence for this concept was found in the current transcript."


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


def _sentence_list(transcript):
    return [sentence.strip() for sentence in re.findall(r"[^.!?]+[.!?]+|[^.!?]+$", transcript) if sentence.strip()]


def _concept_terms(concept, related_terms):
    concept_words = [word for word in _normalise_words(concept) if word not in _STOP_WORDS]
    variants = {tuple(concept_words)} if concept_words else set()
    if len(concept_words) >= 2:
        variants.add(("".join(word[0] for word in concept_words),))

    related_by_acronym = {}
    for term in related_terms:
        words = [word for word in _normalise_words(term) if word not in _STOP_WORDS]
        if len(words) >= 2:
            related_by_acronym["".join(word[0] for word in words)] = words
    if len(concept_words) == 1 and concept_words[0] in related_by_acronym:
        variants.add(tuple(related_by_acronym[concept_words[0]]))

    return concept_words, variants


def _find_explanation(concept, transcript, related_terms, used_sentence_indices):
    sentences = _sentence_list(transcript)
    if not sentences:
        return _FALLBACK_DESCRIPTION

    concept_words, variants = _concept_terms(concept, related_terms)
    if not concept_words:
        return _FALLBACK_DESCRIPTION

    ranked = []
    for index, sentence in enumerate(sentences):
        sentence_words = _normalise_words(sentence)
        sentence_set = set(sentence_words)
        exact_match = any(
            tuple(sentence_words[i:i + len(variant)]) == variant
            for variant in variants
            for i in range(max(0, len(sentence_words) - len(variant) + 1))
        )
        direct_matches = len(set(concept_words) & sentence_set)
        if direct_matches == 0 and not exact_match:
            continue

        score = 170 if exact_match else 0
        score += direct_matches * 45
        score += round(direct_matches * 30 / len(concept_words))

        other_concept_hits = 0
        related_matches = 0
        for related in related_terms:
            related_words = [word for word in _normalise_words(related) if word not in _STOP_WORDS]
            if not related_words or related_words == concept_words:
                continue
            overlap = len(set(related_words) & sentence_set)
            if overlap >= max(1, (len(related_words) + 1) // 2):
                other_concept_hits += 1
                related_matches += overlap
        score += min(8, related_matches * 2)
        score -= min(60, other_concept_hits * 12)
        if index in used_sentence_indices:
            score -= 55
        ranked.append((score, index, sentence))

    if not ranked:
        return _FALLBACK_DESCRIPTION

    unused = [item for item in ranked if item[1] not in used_sentence_indices]
    ranked = unused or ranked
    ranked.sort(key=lambda item: (-item[0], item[1]))
    best_score = ranked[0][0]
    selected = [ranked[0]]
    for candidate in ranked[1:]:
        if len(selected) >= 3 or candidate[1] in used_sentence_indices:
            continue
        if candidate[0] < max(20, best_score * 0.8):
            continue
        if min(abs(candidate[1] - item[1]) for item in selected) > 1:
            continue
        selected.append(candidate)
    used_sentence_indices.add(ranked[0][1])
    selected = sorted(selected, key=lambda item: item[1])
    return " ".join(item[2] for item in selected)


def _node_id(label, used_ids):
    base = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "concept"
    candidate = base
    suffix = 2
    while candidate in used_ids:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used_ids.add(candidate)
    return candidate


def build_mindmap_data(title, transcript, keywords):
    concepts = []
    seen = set()
    for keyword in keywords or []:
        name = str(keyword).strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            concepts.append(name)

    transcript = transcript or ""
    root_id = "lecture-root"
    nodes = [{"id": root_id, "label": title or "Lecture", "description": "The central topic of this lecture.", "children": []}]
    edges = []
    used_ids = {root_id}
    used_sentence_indices = set()
    related_terms = [title or "Lecture", *concepts]
    for concept in concepts[:10]:
        description = _find_explanation(concept, transcript, related_terms, used_sentence_indices)
        node_id = _node_id(concept, used_ids)
        nodes.append({"id": node_id, "label": concept, "description": description, "children": []})
        nodes[0]["children"].append(node_id)
        edges.append({"source": root_id, "target": node_id})
    return {"nodes": nodes, "edges": edges}
