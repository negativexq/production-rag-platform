import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.evaluation.retrieval_metrics import RetrievalMetrics, compute_retrieval_metrics
from app.llm.prompt import NOT_FOUND_PHRASE
from app.retrieval.hybrid_search import SearchResult

Location = tuple[int, int]

SearchFn = Callable[[str], Awaitable[list[SearchResult]]]
GenerateFn = Callable[[str, list[SearchResult]], Awaitable[str]]
GenerationMetricsFn = Callable[[str, str, list[str]], dict[str, float]]
ProgressCallback = Callable[[str, int, int, str], None]


@dataclass(frozen=True)
class GoldenQuestion:
    id: str
    question: str
    expected_locations: list[Location] = field(default_factory=list)
    reference_answer: str | None = None
    expect_not_found: bool = False


@dataclass
class QuestionResult:
    id: str
    question: str
    answer: str
    retrieval: RetrievalMetrics | None
    generation: dict[str, float] | None
    expect_not_found: bool
    not_found_actual: bool


def load_golden_set(path: str) -> list[GoldenQuestion]:
    with open(path) as f:
        raw = json.load(f)

    questions = []
    for item in raw:
        questions.append(
            GoldenQuestion(
                id=item["id"],
                question=item["question"],
                expected_locations=[tuple(loc) for loc in item.get("expected_locations", [])],
                reference_answer=item.get("reference_answer"),
                expect_not_found=item.get("expect_not_found", False),
            )
        )
    return questions


async def run_evaluation(
    questions: list[GoldenQuestion],
    search_fn: SearchFn,
    generate_fn: GenerateFn,
    generation_metrics_fn: GenerationMetricsFn | None,
    progress_callback: ProgressCallback | None = None,
) -> list[QuestionResult]:
    """Two phases on purpose: all retrieval+generation first (one model,
    e.g. qwen2.5:3b-instruct), then all judge-metric scoring second (a
    different model, e.g. qwen2.5:7b-instruct as judge). Interleaving them
    per-question forces Ollama to swap the loaded model on almost every
    call — observed in practice to make a 20-question run take 40+ minutes
    instead of the ~11 expected from isolated per-metric timings. See
    docs/PLANNING.md Sprint 9 closing note.
    """
    total = len(questions)
    pending = []
    for index, question in enumerate(questions, start=1):
        retrieved = await search_fn(question.question)
        answer = await generate_fn(question.question, retrieved)
        not_found_actual = NOT_FOUND_PHRASE in answer

        retrieval_metrics = None
        if question.expected_locations:
            retrieval_metrics = compute_retrieval_metrics(retrieved, question.expected_locations)

        pending.append((question, retrieved, answer, not_found_actual, retrieval_metrics))
        if progress_callback:
            progress_callback("generate", index, total, question.id)

    results = []
    for index, (question, retrieved, answer, not_found_actual, retrieval_metrics) in enumerate(
        pending, start=1
    ):
        generation_scores = None
        if not question.expect_not_found and not not_found_actual and generation_metrics_fn:
            contexts = [chunk.payload["text"] for chunk in retrieved]
            generation_scores = generation_metrics_fn(question.question, answer, contexts)
        if progress_callback:
            progress_callback("judge", index, total, question.id)

        results.append(
            QuestionResult(
                id=question.id,
                question=question.question,
                answer=answer,
                retrieval=retrieval_metrics,
                generation=generation_scores,
                expect_not_found=question.expect_not_found,
                not_found_actual=not_found_actual,
            )
        )

    return results


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def build_report(results: list[QuestionResult]) -> dict:
    precisions = [r.retrieval.precision for r in results if r.retrieval is not None]
    recalls = [r.retrieval.recall for r in results if r.retrieval is not None]
    faithfulness = [r.generation["faithfulness"] for r in results if r.generation is not None]
    answer_relevancy = [
        r.generation["answer_relevancy"] for r in results if r.generation is not None
    ]
    not_found_results = [r for r in results if r.expect_not_found]
    not_found_correct = [r for r in not_found_results if r.not_found_actual]

    return {
        "question_count": len(results),
        "mean_precision": _mean(precisions),
        "mean_recall": _mean(recalls),
        "mean_faithfulness": _mean(faithfulness),
        "mean_answer_relevancy": _mean(answer_relevancy),
        "not_found_question_count": len(not_found_results),
        "not_found_accuracy": (
            len(not_found_correct) / len(not_found_results) if not_found_results else None
        ),
    }
