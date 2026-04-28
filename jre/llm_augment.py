"""LLM-augmented detection via OpenRouter.

Provides an optional LLM layer for pattern detection on cases where
regex may miss novel phrasings. Defaults to qwen/qwen3.6-flash via
OpenRouter API.

Usage:
    from jre.llm_augment import LLMDetector

    detector = LLMDetector()  # Reads OPENROUTER_API_KEY from .env
    result = detector.analyze_case(case)
    # result.findings contains LLM-detected patterns
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class LLMFinding:
    """A finding detected by the LLM layer."""
    category: str  # sentinel, integrity, clinical_pattern, distortion
    concept: str
    severity: float
    reason: str
    evidence: str
    confidence: float  # LLM's self-assessed confidence


@dataclass
class LLMAnalysisResult:
    """Result of LLM analysis on a case."""
    case_id: str
    findings: List[LLMFinding]
    raw_response: str
    model: str
    success: bool
    error: Optional[str] = None


def _load_env_value(name: str) -> Optional[str]:
    """Load a setting from environment or .env file."""
    value = os.environ.get(name)
    if value:
        return value

    # Try loading from .env files in common locations
    for env_path in [
        Path(__file__).resolve().parents[1] / ".env",
        Path.home() / ".env",
    ]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith(f"{name}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _load_api_key() -> Optional[str]:
    """Load OpenRouter API key from environment or .env file."""
    return _load_env_value("OPENROUTER_API_KEY")


# System prompt for clinical pattern detection
_SYSTEM_PROMPT = """You are a clinical safety pattern detector for a healthcare AI intake system.

Your job is to analyze patient intake statements and detect patterns that regex-based rules might miss:

1. **Sentinel risks**: Time-sensitive medical emergencies hidden in casual language
   (e.g., stroke symptoms described as "feeling weird", cardiac symptoms described as "indigestion")

2. **Integrity issues**: Signs of identity confusion, adversarial behavior, metric gaming,
   or unreliable communication

3. **Clinical distortions**: Where patient language minimizes or masks dangerous symptoms
   (e.g., "sugar is fine" when glucose is 400, "not pain just pressure")

4. **Human disclosure pressure**: Where embarrassment, stigma, misunderstood medical facts,
   or fear of a bad diagnosis may cause the patient to curate the history or answer around
   what they hope is true rather than what is clinically complete

5. **Hidden red flags**: Symptoms that change the safety profile but are buried in context

For each finding, provide:
- category: one of "sentinel", "integrity", "clinical_pattern", "distortion"
- concept: the clinical concept affected
- severity: 0.0 to 1.0
- reason: why this matters clinically
- evidence: the specific text that triggered the finding
- confidence: your confidence in this finding (0.0 to 1.0)

Respond ONLY with valid JSON in this format:
{
  "findings": [
    {
      "category": "sentinel",
      "concept": "stroke_language",
      "severity": 0.95,
      "reason": "Patient describes sudden one-sided weakness using casual language",
      "evidence": "my left side feels funny since this morning",
      "confidence": 0.85
    }
  ]
}

If no concerning patterns are found, return: {"findings": []}

For non-clean cases, include candidate interpretation-boundary signals even if a deterministic rule may also catch them. Examples: stale objective data, vague reassurance, denial reliability problems, hidden emergency language, unsafe channel, nonresponse after risk, source conflict, embarrassment/stigma/fear-curated history, or missing evidence that materially changes safe autonomy.

Be conservative about diagnosis, but do not be silent about safety-boundary concerns."""


class LLMDetector:
    """LLM-augmented clinical pattern detector using OpenRouter."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: str = "https://openrouter.ai/api/v1/chat/completions",
        timeout: Optional[int] = None,
    ) -> None:
        self.api_key = api_key or _load_api_key()
        # Model should be updated by user per project policy via OPENROUTER_MODEL env var
        self.model = model or _load_env_value("OPENROUTER_MODEL") or "qwen/qwen3.6-flash"
        self.base_url = base_url
        self.timeout = timeout or int(os.environ.get("OPENROUTER_TIMEOUT_SECONDS", "75"))

    @property
    def available(self) -> bool:
        """Check if API key is configured."""
        return self.api_key is not None and len(self.api_key) > 0

    def _build_case_prompt(self, case) -> str:
        """Build the analysis prompt from a CaseInput."""
        lines = [
            f"Case ID: {case.case_id}",
            f"Domain: {case.patient_context.domain}",
            f"Age: {case.patient_context.age}",
            f"Chief concern: {case.patient_context.chief_concern}",
            f"Modality: {case.patient_context.modality}",
            f"Language barrier: {case.patient_context.language_barrier}",
            f"Known conditions: {', '.join(case.patient_context.known_conditions) or 'none'}",
            "",
            "Patient statements:",
        ]
        for s in case.statements:
            lines.append(f"  Q: {s.question}")
            lines.append(f"  A: {s.answer}")
            lines.append(f"  (source: {s.source}, concept: {s.concept or 'unknown'})")
            lines.append("")

        lines.append("Analyze these statements for hidden clinical risks, distortion patterns, and safety concerns that simple regex might miss.")
        return "\n".join(lines)

    def analyze_case(self, case) -> LLMAnalysisResult:
        """Analyze a single case through the LLM."""
        if not self.available:
            return LLMAnalysisResult(
                case_id=case.case_id,
                findings=[],
                raw_response="",
                model=self.model,
                success=False,
                error="No API key configured. Set OPENROUTER_API_KEY in .env or environment.",
            )

        prompt = self._build_case_prompt(case)

        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 900,
        }).encode("utf-8")

        req = urllib.request.Request(
            self.base_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/jre-clinical-safety",
                "X-Title": "JRE Clinical Safety",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))

            raw_content = response_data["choices"][0]["message"]["content"]
            findings = self._parse_findings(raw_content)

            return LLMAnalysisResult(
                case_id=case.case_id,
                findings=findings,
                raw_response=raw_content,
                model=self.model,
                success=True,
            )

        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
            except Exception:
                pass
            return LLMAnalysisResult(
                case_id=case.case_id,
                findings=[],
                raw_response=error_body,
                model=self.model,
                success=False,
                error=f"HTTP {e.code}: {error_body[:200]}",
            )

        except Exception as e:
            return LLMAnalysisResult(
                case_id=case.case_id,
                findings=[],
                raw_response="",
                model=self.model,
                success=False,
                error=str(e),
            )

    def _parse_findings(self, raw: str) -> List[LLMFinding]:
        """Parse LLM JSON response into findings."""
        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (code fences)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []

        findings = []
        for f in data.get("findings", []):
            try:
                findings.append(LLMFinding(
                    category=str(f.get("category", "unknown")),
                    concept=str(f.get("concept", "unknown")),
                    severity=float(f.get("severity", 0.5)),
                    reason=str(f.get("reason", "")),
                    evidence=str(f.get("evidence", "")),
                    confidence=float(f.get("confidence", 0.5)),
                ))
            except (ValueError, TypeError):
                continue

        return findings

    def analyze_batch(self, cases) -> List[LLMAnalysisResult]:
        """Analyze multiple cases sequentially."""
        return [self.analyze_case(case) for case in cases]

    def suggest_rules(self, case, findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Ask LLM to propose new detection rules based on a case and its findings.

        Returns a dict with suggested regex patterns, contradiction rules, or
        gestalt patterns that could improve detection for similar cases.
        """
        if not self.available:
            return {
                "success": False,
                "error": "No API key configured.",
                "suggestions": [],
            }

        findings_text = "\n".join(
            f"  - [{f.get('category', '?')}] {f.get('concept', '?')}: {f.get('reason', '?')} (severity {f.get('severity', '?')})"
            for f in findings
        )

        prompt = self._build_case_prompt(case)
        prompt += f"\n\nCurrent findings detected:\n{findings_text}\n"
        prompt += """
Based on this case and its findings, suggest NEW detection rules that would improve coverage.
For each suggestion provide:
- rule_type: one of "regex_pattern", "contradiction_rule", "gestalt_pattern", "trap"
- name: a short identifier (e.g., "CONTRA_NEW_RULE" or "fever_proxy_language")
- pattern: the regex pattern (for regex_pattern/trap) or trigger conditions (for contradiction/gestalt)
- severity: suggested severity 0.0-1.0
- rationale: why this rule would help
- example_trigger: an example patient statement that would fire this rule

Respond ONLY with valid JSON: {"suggestions": [...]}
If no new rules are needed, return: {"suggestions": []}"""

        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a clinical safety rule engineer. You design regex patterns, contradiction rules, and gestalt patterns for a healthcare intake safety system."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 2000,
        }).encode("utf-8")

        req = urllib.request.Request(
            self.base_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/jre-clinical-safety",
                "X-Title": "JRE Clinical Safety",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))

            raw_content = response_data["choices"][0]["message"]["content"]
            parsed = self._parse_json_response(raw_content)
            return {
                "success": True,
                "suggestions": parsed.get("suggestions", []),
                "raw_response": raw_content,
                "model": self.model,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "suggestions": [],
            }

    def suggest_case(self, domain: str, gap_description: str = "") -> Dict[str, Any]:
        """Ask LLM to generate a synthetic case that stress-tests a gap.

        Returns a dict with a complete case definition including patient context,
        statements, and expected ground truth.
        """
        if not self.available:
            return {
                "success": False,
                "error": "No API key configured.",
                "case": None,
            }

        prompt = f"""Generate a synthetic clinical intake case for the "{domain}" domain.
{f"Focus on this gap: {gap_description}" if gap_description else "Design a challenging case that tests edge cases in clinical safety detection."}

The case should include:
- case_id: a descriptive ID like "SYNTH-001-short-description"
- patient_context: age, chief_concern, domain ("{domain}"), modality, known_conditions, literacy_hint, language_barrier, has_caregiver
- statements: 4-8 question/answer pairs that a clinical intake system would collect. Each with: question, answer, concept (clinical slot name), source (patient/caregiver/device/chart)
- ground_truth: requires_escalation (true/false), expected_state, rationale
- narrative: a 1-2 sentence scenario description

Make the case realistic and challenging — it should test the system's ability to detect subtle clinical safety signals.

Respond ONLY with valid JSON matching this structure:
{{
  "case": {{
    "case_id": "...",
    "patient_context": {{...}},
    "statements": [{{...}}],
    "ground_truth": {{...}},
    "narrative": "..."
  }}
}}"""

        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a clinical case designer for a healthcare AI safety system. You create realistic, challenging synthetic patient intake scenarios."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
            "max_tokens": 2000,
        }).encode("utf-8")

        req = urllib.request.Request(
            self.base_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/jre-clinical-safety",
                "X-Title": "JRE Clinical Safety",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))

            raw_content = response_data["choices"][0]["message"]["content"]
            parsed = self._parse_json_response(raw_content)
            return {
                "success": True,
                "case": parsed.get("case"),
                "raw_response": raw_content,
                "model": self.model,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "case": None,
            }

    def _parse_json_response(self, raw: str) -> Dict[str, Any]:
        """Parse a JSON response, stripping markdown code fences if present."""
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}
