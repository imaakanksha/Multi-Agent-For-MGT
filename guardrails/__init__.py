"""
Guardrails Module — Input validation, prompt injection defense,
schema enforcement, and LLM refusal handling.

This module provides three layers of protection:

  1. INPUT GUARDRAILS: Validate and sanitize user prompts before
     they enter the pipeline. Detects prompt injection attempts,
     off-topic inputs, and malformed requests.

  2. OUTPUT GUARDRAILS: Enforce strict JSON schemas on every LLM
     response. Reject malformed outputs and retry with guidance.

  3. REFUSAL HANDLING: Detect when an LLM refuses to answer
     (safety filters, content policy) and route gracefully.

References:
  - OWASP LLM Top 10: Prompt Injection (LLM01)
  - Simon Willison, "Prompt Injection" (2023)
  - Pydantic schema enforcement for structured LLM outputs
"""

from __future__ import annotations
import re
import json
import logging
from typing import Any
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# 1. INPUT GUARDRAILS — Prompt Validation & Injection Defense
# ══════════════════════════════════════════════════════════════════════

# Known prompt injection patterns (regex-based heuristic layer)
_INJECTION_PATTERNS = [
    # Direct instruction override attempts
    r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)",
    r"(?i)disregard\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?)",
    r"(?i)forget\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?)",
    # System prompt extraction
    r"(?i)(show|reveal|print|output|repeat|display)\s+(your|the)\s+(system\s+)?(prompt|instructions?|rules?)",
    r"(?i)what\s+(are|is)\s+your\s+(system\s+)?(prompt|instructions?)",
    # Role-play attacks
    r"(?i)you\s+are\s+now\s+(DAN|a\s+hacker|an?\s+unrestricted|evil)",
    r"(?i)act\s+as\s+if\s+(you\s+have\s+)?no\s+(restrictions?|rules?|limits?)",
    r"(?i)pretend\s+(you|that)\s+(are|have)\s+no\s+(restrictions?|filters?)",
    # Delimiter/escape attacks
    r"```\s*system",
    r"\[SYSTEM\]",
    r"<\|im_start\|>",
    r"<\|endoftext\|>",
    # Data exfiltration
    r"(?i)(send|post|fetch|curl|wget|http)\s+(to|from)\s+https?://",
]

# Compiled patterns for performance
_COMPILED_PATTERNS = [re.compile(p) for p in _INJECTION_PATTERNS]

# Content that is off-topic for a research workflow
_OFFTOPIC_PATTERNS = [
    r"(?i)(write|generate|create)\s+(me\s+)?(a\s+)?(poem|song|story|joke|essay|code)",
    r"(?i)(what|who)\s+(are|is)\s+you",
    r"(?i)tell\s+me\s+a\s+(joke|story|secret)",
]

_COMPILED_OFFTOPIC = [re.compile(p) for p in _OFFTOPIC_PATTERNS]


class InputGuardrailResult(BaseModel):
    """Result of input validation."""
    is_valid: bool
    sanitized_prompt: str
    violations: list[str] = []
    risk_score: float = 0.0  # 0.0 = safe, 1.0 = definite injection


def validate_prompt(prompt: str) -> InputGuardrailResult:
    """
    Validate and sanitize a user research prompt.

    Checks:
      1. Length bounds (10-5000 chars)
      2. Prompt injection pattern detection
      3. Off-topic content detection
      4. Control character stripping

    Returns:
        InputGuardrailResult with validation outcome.
    """
    violations = []
    risk_score = 0.0

    # ── Length validation ──────────────────────────────────────────
    if len(prompt.strip()) < 10:
        violations.append("Prompt too short (minimum 10 characters)")
        return InputGuardrailResult(
            is_valid=False, sanitized_prompt=prompt,
            violations=violations, risk_score=0.0,
        )

    if len(prompt) > 5000:
        violations.append("Prompt too long (maximum 5000 characters)")
        return InputGuardrailResult(
            is_valid=False, sanitized_prompt=prompt[:5000],
            violations=violations, risk_score=0.2,
        )

    # ── Strip control characters ──────────────────────────────────
    sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', prompt)

    # ── Prompt injection detection ────────────────────────────────
    injection_hits = []
    for i, pattern in enumerate(_COMPILED_PATTERNS):
        if pattern.search(sanitized):
            injection_hits.append(_INJECTION_PATTERNS[i])
            risk_score += 0.3

    if injection_hits:
        violations.append(
            f"Potential prompt injection detected ({len(injection_hits)} pattern(s) matched)"
        )
        logger.warning(
            "GUARDRAIL: Prompt injection detected. Patterns: %s",
            injection_hits[:3],
        )

    # ── Off-topic detection ───────────────────────────────────────
    for pattern in _COMPILED_OFFTOPIC:
        if pattern.search(sanitized):
            violations.append("Prompt appears off-topic for research workflow")
            risk_score += 0.15
            break

    risk_score = min(risk_score, 1.0)
    is_valid = risk_score < 0.5  # Block if risk ≥ 0.5

    if not is_valid:
        logger.warning(
            "GUARDRAIL: Prompt BLOCKED (risk=%.2f). Violations: %s",
            risk_score, violations,
        )

    return InputGuardrailResult(
        is_valid=is_valid,
        sanitized_prompt=sanitized,
        violations=violations,
        risk_score=risk_score,
    )


# ══════════════════════════════════════════════════════════════════════
# 2. OUTPUT GUARDRAILS — Schema Enforcement
# ══════════════════════════════════════════════════════════════════════

class SchemaValidationResult(BaseModel):
    """Result of output schema validation."""
    is_valid: bool
    parsed_data: dict | None = None
    errors: list[str] = []
    raw_content: str = ""


def enforce_json_schema(
    raw_output: str,
    schema_model: type[BaseModel] | None = None,
    required_keys: list[str] | None = None,
) -> SchemaValidationResult:
    """
    Enforce JSON schema on LLM output.

    This validates that:
      1. The output is valid JSON
      2. Required keys are present
      3. Data conforms to a Pydantic schema (if provided)

    Args:
        raw_output: Raw string from LLM response.
        schema_model: Optional Pydantic model to validate against.
        required_keys: Optional list of required top-level keys.

    Returns:
        SchemaValidationResult with parsed data or errors.
    """
    errors = []

    # ── Step 1: Parse JSON ────────────────────────────────────────
    # Strip markdown code fences if LLM wrapped output
    cleaned = raw_output.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else cleaned

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON: {str(e)[:100]}")
        return SchemaValidationResult(
            is_valid=False, errors=errors, raw_content=raw_output[:500],
        )

    # ── Step 2: Check required keys ───────────────────────────────
    if required_keys:
        missing = [k for k in required_keys if k not in data]
        if missing:
            errors.append(f"Missing required keys: {missing}")

    # ── Step 3: Pydantic schema validation ────────────────────────
    if schema_model and not errors:
        try:
            schema_model.model_validate(data)
        except ValidationError as e:
            for err in e.errors()[:5]:
                loc = " → ".join(str(l) for l in err["loc"])
                errors.append(f"Schema error at '{loc}': {err['msg']}")

    return SchemaValidationResult(
        is_valid=len(errors) == 0,
        parsed_data=data if not errors else None,
        errors=errors,
        raw_content=raw_output[:500],
    )


# ══════════════════════════════════════════════════════════════════════
# 3. REFUSAL HANDLING — LLM Safety Filter Detection
# ══════════════════════════════════════════════════════════════════════

_REFUSAL_INDICATORS = [
    "I cannot",
    "I can't",
    "I'm unable to",
    "I am unable to",
    "I'm not able to",
    "as an AI",
    "as a language model",
    "against my guidelines",
    "content policy",
    "I must decline",
    "I apologize, but I cannot",
    "I'm sorry, but I can't",
    "not appropriate for me to",
]


class RefusalDetectionResult(BaseModel):
    """Result of LLM refusal detection."""
    is_refusal: bool
    refusal_type: str = "none"  # none | safety | content_policy | capability
    indicators_found: list[str] = []


def detect_refusal(llm_output: str) -> RefusalDetectionResult:
    """
    Detect if an LLM has refused to generate the requested output.

    This catches cases where the LLM returns a polite refusal instead
    of structured JSON, which would cause downstream parsing failures.

    Args:
        llm_output: Raw string from LLM response.

    Returns:
        RefusalDetectionResult indicating whether output is a refusal.
    """
    output_lower = llm_output.lower().strip()
    indicators = []

    for phrase in _REFUSAL_INDICATORS:
        if phrase.lower() in output_lower:
            indicators.append(phrase)

    if not indicators:
        return RefusalDetectionResult(is_refusal=False)

    # Classify the refusal type
    if any(p in output_lower for p in ["content policy", "guidelines", "safety"]):
        refusal_type = "content_policy"
    elif any(p in output_lower for p in ["unable to", "can't", "cannot"]):
        refusal_type = "capability"
    else:
        refusal_type = "safety"

    logger.warning(
        "GUARDRAIL: LLM refusal detected (type=%s). Indicators: %s",
        refusal_type, indicators[:3],
    )

    return RefusalDetectionResult(
        is_refusal=True,
        refusal_type=refusal_type,
        indicators_found=indicators,
    )
