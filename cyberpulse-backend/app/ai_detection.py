"""Heuristic academic-integrity scoring for quiz submissions.

Returns a 0-100 "AI / cheating likelihood" score. It is intentionally
transparent and explainable — no black box — so instructors can defend
any flag they raise.

Signals used:
  * unrealistically fast answering (per-question seconds)
  * suspiciously uniform per-question timing (bot-like rhythm)
  * a perfect score achieved far below the cohort's median time
  * answers submitted with almost no elapsed time at all
"""

from statistics import median, pstdev

FLAG_THRESHOLD = 70.0


def compute_ai_detection_score(
    *,
    total_questions: int,
    time_spent_seconds: int,
    question_times: list[int] | None,
    score: int,
    total_points: int,
    cohort_median_time: float | None = None,
) -> float:
    if total_questions <= 0:
        return 0.0

    score_value = 0.0
    avg_per_question = time_spent_seconds / total_questions if time_spent_seconds else 0.0

    # 1. Speed: under 4s/question is barely enough to read the prompt.
    if avg_per_question <= 0:
        score_value += 45
    elif avg_per_question < 4:
        score_value += 40
    elif avg_per_question < 8:
        score_value += 22
    elif avg_per_question < 15:
        score_value += 8

    # 2. Rhythm: near-zero variance across questions looks automated.
    times = [t for t in (question_times or []) if t is not None]
    if len(times) >= 4:
        spread = pstdev(times)
        if spread < 1.0:
            score_value += 25
        elif spread < 2.5:
            score_value += 12

    # 3. Perfect score much faster than peers.
    accuracy = (score / total_points) if total_points else 0.0
    if cohort_median_time and time_spent_seconds:
        ratio = time_spent_seconds / cohort_median_time
        if accuracy >= 0.95 and ratio < 0.4:
            score_value += 25
        elif accuracy >= 0.9 and ratio < 0.6:
            score_value += 12

    # 4. Perfect score with an implausibly short total time.
    if accuracy >= 0.95 and avg_per_question < 6:
        score_value += 15

    return round(min(score_value, 100.0), 1)


def is_flagged(ai_detection_score: float) -> bool:
    return ai_detection_score >= FLAG_THRESHOLD
