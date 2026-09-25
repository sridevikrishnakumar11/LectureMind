"""Build transcript-grounded revision recommendations from saved quiz attempts."""

from collections import defaultdict

from models.mindmap_visualizer import build_mindmap_data


def _concept_key(concept):
    return str(concept or "").strip().casefold()


def build_revision_recommendations(attempts, lectures):
    """Return weak concepts using only submitted answer metadata and lecture text."""
    lecture_by_id = {str(lecture.get("id")): lecture for lecture in lectures or []}
    totals = defaultdict(lambda: {"concept": "", "lecture_id": "", "correct": 0, "total": 0, "incorrect": 0})

    for attempt in attempts or []:
        lecture_id = str(attempt.get("lecture_id") or "")
        for answer in attempt.get("answers") or []:
            concept = str(answer.get("concept") or "").strip()
            key = (lecture_id, _concept_key(concept))
            if not concept or not lecture_id or not key[1]:
                continue
            record = totals[key]
            record["concept"] = concept
            record["lecture_id"] = lecture_id
            record["total"] += 1
            if answer.get("is_correct"):
                record["correct"] += 1
            else:
                record["incorrect"] += 1

    recommendations = []
    for record in totals.values():
        if record["incorrect"] == 0:
            continue
        lecture = lecture_by_id.get(record["lecture_id"])
        if not lecture:
            continue
        graph_keywords = list(lecture.get("keywords") or [])
        if not any(_concept_key(item) == _concept_key(record["concept"]) for item in graph_keywords):
            graph_keywords.append(record["concept"])
        graph = build_mindmap_data(lecture.get("title"), lecture.get("transcript"), graph_keywords)
        node = next(
            (item for item in graph.get("nodes", [])[1:]
             if _concept_key(item.get("label")) == _concept_key(record["concept"])),
            None,
        )
        if not node:
            continue
        recommendations.append({
            "concept": record["concept"],
            "lecture_id": record["lecture_id"],
            "lecture_title": lecture.get("title") or "Lecture",
            "incorrect": record["incorrect"],
            "correct": record["correct"],
            "total": record["total"],
            "percentage": round(record["correct"] * 100 / record["total"]),
            "explanation": node.get("description"),
        })

    return sorted(recommendations, key=lambda item: (-item["incorrect"], item["concept"].casefold()))
