from typing import Protocol

from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
from deepeval.models import OllamaModel
from deepeval.test_case import LLMTestCase

# Faithfulness/answer relevancy need an LLM judge to compare claims against
# context, which needs more reasoning capacity than the 3B model used for
# actual RAG generation reliably provides — qwen2.5:3b-instruct produced an
# internally inconsistent verdict/reason pair in real testing (see
# docs/PLANNING.md Sprint 9 closing note). 7B fixed it in the same test.
DEFAULT_JUDGE_MODEL = "qwen2.5:7b-instruct"


class MetricProtocol(Protocol):
    score: float

    def measure(self, test_case: LLMTestCase) -> None: ...


def compute_generation_metrics(
    question: str,
    answer: str,
    retrieved_contexts: list[str],
    metrics: dict[str, MetricProtocol],
) -> dict[str, float]:
    test_case = LLMTestCase(
        input=question, actual_output=answer, retrieval_context=retrieved_contexts
    )
    results = {}
    for name, metric in metrics.items():
        metric.measure(test_case)
        results[name] = metric.score
    return results


def build_default_metrics(
    judge_model_name: str = DEFAULT_JUDGE_MODEL, base_url: str = "http://localhost:11434"
) -> dict[str, MetricProtocol]:
    judge = OllamaModel(model=judge_model_name, base_url=base_url)
    return {
        "faithfulness": FaithfulnessMetric(model=judge),
        "answer_relevancy": AnswerRelevancyMetric(model=judge),
    }
