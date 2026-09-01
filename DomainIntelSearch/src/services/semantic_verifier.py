"""Production construction boundary for independent assertion verification."""

from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from src.agent_evidence import (
    AssertionVerifier,
    ConfiguredSemanticEvaluator,
    SemanticEvaluation,
    SemanticEvaluationRequest,
    probe_agent_evidence,
)
from .provider_factory import create_provider


_DECISIONS = {"supported", "partial", "contradicted", "unknown"}


class _TextLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["text_offset"]
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class _HtmlLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["html_selector"]
    selector: str = Field(min_length=1, max_length=500)


class _PdfLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["pdf_page"]
    page: int = Field(ge=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class _ApiLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["api_field"]
    path: str = Field(min_length=1, max_length=1000)


_Locator = Annotated[
    _TextLocator | _HtmlLocator | _PdfLocator | _ApiLocator,
    Field(discriminator="type")]


class _Conversion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    original_value: int | float | str
    target_value: int | float | str
    target_unit: str
    target_currency: str
    formula: Literal["multiply", "divide"]
    rate: int | float | str
    benchmark_source: str


class _AssertionNumericObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["assertion_value"]
    value: int | float | str
    unit: str
    currency: str = ""
    period: str
    statistical_definition: str
    conversion: _Conversion | None = None


class _BenchmarkObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["conversion_rate"]
    rate: int | float | str
    formula: Literal["multiply", "divide"]
    from_currency: str
    to_currency: str
    from_unit: str
    to_unit: str
    period: str
    tolerance: int | float | str = 0


_NumericObservation = Annotated[
    _AssertionNumericObservation | _BenchmarkObservation,
    Field(discriminator="kind")]

_ConditionKey = Annotated[str, Field(min_length=1, max_length=80,
                                     pattern=r"^[A-Za-z0-9_.-]+$")]
_ConditionValue = Annotated[str, Field(min_length=1, max_length=200)]


class _ProviderEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str = Field(min_length=1)
    semantic: Literal["supported", "partial", "contradicted", "unknown"]
    assertion_type: Literal[
        "identity", "regulatory_status", "formal_company_disclosure", "event",
        "transaction", "value_chain_relationship", "market_size", "market_share",
        "valuation", "unofficial_statistics", "financial",
        "technical_performance", "causal", "forecast", "investment_judgment",
        "opinion"]
    reason: str = Field(min_length=1)
    entity_ids: list[str] = Field(max_length=20)
    numeric_observations: list[_NumericObservation] = Field(max_length=100)
    document_content_type: Literal[
        "official_record", "regulatory_filing", "company_disclosure",
        "direct_first_party", "audited_statement", "standard", "official_spec",
        "academic_result", "news_report", "market_estimate", ""]
    experimental_conditions: dict[_ConditionKey, _ConditionValue] = Field(max_length=20)
    locator: _Locator
    located_text: str = Field(min_length=1)


_PROVIDER_RESULTS = TypeAdapter(list[_ProviderEvaluation])


def _json_payload(text: str):
    value = str(text or "").strip()
    if value.startswith("```"):
        lines = value.splitlines()
        value = "\n".join(lines[1:-1]).strip()
        if value.casefold().startswith("json"):
            value = value[4:].lstrip()
    return json.loads(value)


def _prompt(request: SemanticEvaluationRequest) -> str:
    payload = {
        "assertion_id": request.assertion_id,
        "assertion_text": request.assertion_text,
        "atomic": request.atomic,
        "evidence": [{
            "evidence_id": item.evidence_id,
            "role": item.role,
            "excerpt": item.excerpt,
            "locator": item.locator,
        } for item in request.evidence],
    }
    return (
        "Independently judge whether each located excerpt supports the atomic assertion. "
        "Return only a JSON array with one strict structured probe object per evidence "
        "item, including semantic, reason, entity_ids, numeric_observations, "
        "document_content_type, assertion_type, experimental_conditions, locator, "
        "and located_text. experimental_conditions must be a key/value object and "
        "every pair must be reproduced verbatim in the located excerpt; use {} when "
        "not applicable. "
        "assertion_type must independently classify the assertion using the controlled "
        "type vocabulary and must be identical for every support item. semantic must be "
        "supported, partial, contradicted, or unknown. Benchmark evidence should use "
        "unknown semantics. Echo deterministic locator text exactly; do not infer missing facts.\n" +
        json.dumps(payload, ensure_ascii=False, sort_keys=True))


def build_production_assertion_verifier(
        workspace: str | Path, environment: dict[str, str] | None = None
        ) -> AssertionVerifier:
    """Build from the explicit local provider registry; absence is retryable."""
    env = os.environ if environment is None else environment
    provider_name = str(env.get("INTDOG_VERIFIER_PROVIDER") or "").strip().casefold()
    if not provider_name:
        return AssertionVerifier(fetch=probe_agent_evidence)
    try:
        provider = create_provider({}, provider_name, workspace)
    except Exception as exc:
        return AssertionVerifier(
            fetch=probe_agent_evidence,
            configuration_diagnostic=(
                f"semantic verifier provider configuration failed: {type(exc).__name__}"))

    def evaluate(request: SemanticEvaluationRequest) -> list[SemanticEvaluation]:
        result = provider.complete(_prompt(request))
        try:
            rows = _PROVIDER_RESULTS.validate_python(_json_payload(result.text))
        except Exception as exc:
            raise ValueError("structured semantic probe validation failed") from exc
        source = {item.evidence_id: item for item in request.evidence}
        call_id = str(getattr(result, "response_id", "") or
                      f"verifier:{provider_name}:" +
                      sha256(result.text.encode("utf-8")).hexdigest()[:24])
        evaluations = []
        for row in rows:
            if row.evidence_id not in source:
                raise ValueError("semantic verifier returned an unknown evidence id")
            item = source[row.evidence_id]
            locator = row.locator.model_dump(mode="json")
            if locator != item.locator or row.located_text != item.excerpt:
                raise ValueError("structured semantic probe changed deterministic locator data")
            evaluations.append(SemanticEvaluation(
                evidence_id=item.evidence_id, decision=row.semantic,
                reason=row.reason,
                content_hash=item.content_hash, locator=item.locator,
                evaluator_call_id=call_id,
                entity_ids=tuple(row.entity_ids),
                numeric_observations=tuple(observation.model_dump(
                                               mode="json", exclude_unset=True)
                                           for observation in row.numeric_observations),
                document_content_type=row.document_content_type,
                experimental_conditions=tuple(sorted(
                    (str(key), str(value))
                    for key, value in row.experimental_conditions.items())),
                located_text=row.located_text, page_texts=(),
                structured_observations=True, assertion_type=row.assertion_type))
        return evaluations

    return AssertionVerifier(
        fetch=probe_agent_evidence,
        semantic_evaluator=ConfiguredSemanticEvaluator(
            evaluator_id=provider_name, method="independent_model", evaluate=evaluate,
            requires_structured_observations=True))
