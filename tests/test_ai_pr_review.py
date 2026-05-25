from pathlib import Path
import sys

import pytest
import pydantic


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import ai_pr_review as reviewer  # noqa: E402


def test_load_config_loads_existing_file(tmp_path):
    config_path = tmp_path / ".ai-reviewer.yml"
    config_path.write_text(
        """
review:
  mode: summary
  max_files: 3
  max_diff_chars: 100
  min_severity: alta
ignore:
  - "dist/**"
focus:
  - security
bot:
  marker: "<!-- custom -->"
""",
        encoding="utf-8",
    )

    config = reviewer.load_config(str(config_path))

    assert config["review"]["max_files"] == 3
    assert config["review"]["max_diff_chars"] == 100
    assert config["review"]["min_severity"] == "alta"
    assert config["ignore"] == ["dist/**"]
    assert config["focus"] == ["security"]
    assert config["bot"]["marker"] == "<!-- custom -->"


def test_load_config_missing_file_returns_defaults(tmp_path):
    config = reviewer.load_config(str(tmp_path / "missing.yml"))

    assert config["review"]["mode"] == "summary"
    assert config["review"]["max_files"] == 25
    assert config["review"]["max_diff_chars"] == 60000
    assert config["review"]["min_severity"] == "media"
    assert config["bot"]["marker"] == reviewer.COMMENT_MARKER


def test_load_config_empty_yaml_returns_defaults(tmp_path):
    config_path = tmp_path / ".ai-reviewer.yml"
    config_path.write_text("", encoding="utf-8")

    config = reviewer.load_config(str(config_path))

    assert config["review"]["max_files"] == 25
    assert config["ignore"] == []
    assert config["focus"] == []


def test_ignored_matches_config_patterns():
    patterns = [
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "dist/**",
        "build/**",
        "node_modules/**",
        "*.png",
        "*.jpg",
        "*.jpeg",
        "*.svg",
        "*.pdf",
    ]

    assert reviewer.ignored("package-lock.json", patterns)
    assert reviewer.ignored("dist/app.js", patterns)
    assert reviewer.ignored("node_modules/lib/index.js", patterns)
    assert reviewer.ignored("logo.png", patterns)
    assert not reviewer.ignored("src/app.py", patterns)


def test_build_diff_omits_ignored_and_no_patch_files():
    config = {
        "review": {"max_files": 25, "max_diff_chars": 60000},
        "ignore": ["package-lock.json"],
    }
    files = [
        {
            "filename": "package-lock.json",
            "patch": "@@ ignored",
            "status": "modified",
        },
        {
            "filename": "README.md",
            "status": "modified",
        },
        {
            "filename": "src/app.py",
            "patch": "@@\n+print('hello')",
            "status": "modified",
            "additions": 1,
            "deletions": 0,
            "changes": 1,
        },
    ]

    diff_text, skipped_files, was_truncated = reviewer.build_diff(files, config)

    assert "src/app.py" in diff_text
    assert "print('hello')" in diff_text
    assert "package-lock.json" not in diff_text
    assert "package-lock.json (ignored)" in skipped_files
    assert "README.md (no patch)" in skipped_files
    assert was_truncated is False


def test_build_diff_respects_max_files():
    config = {
        "review": {"max_files": 1, "max_diff_chars": 60000},
        "ignore": [],
    }
    files = [
        {"filename": "src/one.py", "patch": "@@\n+one"},
        {"filename": "src/two.py", "patch": "@@\n+two"},
    ]

    diff_text, skipped_files, was_truncated = reviewer.build_diff(files, config)

    assert "src/one.py" in diff_text
    assert "src/two.py" not in diff_text
    assert "src/two.py (max_files)" in skipped_files
    assert was_truncated is True


def test_build_diff_truncates_by_max_diff_chars():
    config = {
        "review": {"max_files": 25, "max_diff_chars": 80},
        "ignore": [],
    }
    files = [
        {
            "filename": "src/large.py",
            "patch": "@@\n+" + ("x" * 200),
        }
    ]

    diff_text, skipped_files, was_truncated = reviewer.build_diff(files, config)

    assert len(diff_text) <= 80
    assert "src/large.py" in diff_text
    assert "src/large.py (max_diff_chars)" in skipped_files
    assert was_truncated is True


def test_reviewed_files_from_diff_extracts_unique_files():
    diff_text = "\n".join(
        [
            "diff --git a/src/app.py b/src/app.py",
            "@@",
            "diff --git a/src/auth.py b/src/auth.py",
            "@@",
            "diff --git a/src/app.py b/src/app.py",
        ]
    )

    assert reviewer.reviewed_files_from_diff(diff_text) == [
        "src/app.py",
        "src/auth.py",
    ]


def test_review_result_json_schema_is_strict():
    schema = reviewer.review_result_json_schema()
    required = {
        "risk",
        "summary",
        "main_changes",
        "reviewed_files",
        "skipped_files",
        "diff_truncated",
        "confidence",
        "findings",
        "manual_tests",
        "omitted_comments",
    }
    finding_required = {
        "title",
        "file",
        "severity",
        "category",
        "confidence",
        "evidence",
        "impact",
        "recommendation",
        "suggested_test",
    }

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == required
    assert schema["properties"]["risk"]["enum"] == ["Bajo", "Medio", "Alto"]
    assert schema["properties"]["confidence"]["enum"] == ["baja", "media", "alta"]
    assert schema["properties"]["reviewed_files"]["type"] == "array"
    assert schema["properties"]["skipped_files"]["type"] == "array"
    assert schema["properties"]["diff_truncated"]["type"] == "boolean"

    finding = schema["properties"]["findings"]["items"]
    assert finding["additionalProperties"] is False
    assert set(finding["required"]) == finding_required
    assert finding["properties"]["severity"]["enum"] == ["baja", "media", "alta"]
    assert finding["properties"]["confidence"]["enum"] == ["baja", "media", "alta"]
    assert finding["properties"]["category"]["enum"] == [
        "bug",
        "security",
        "regression",
        "missing_test",
        "edge_case",
        "architecture",
    ]


def valid_review_payload():
    return {
        "risk": "Medio",
        "summary": "Resumen de prueba.",
        "main_changes": ["Cambio principal."],
        "reviewed_files": ["src/app.py"],
        "skipped_files": ["dist/app.js (ignored)"],
        "diff_truncated": False,
        "confidence": "media",
        "findings": [
            {
                "title": "Posible regresión",
                "file": "src/app.py",
                "severity": "alta",
                "category": "bug",
                "confidence": "media",
                "evidence": "La evidencia aparece en el diff.",
                "impact": "Puede romper el flujo de login.",
                "recommendation": "Agregar una validación.",
                "suggested_test": "Probar login con credenciales inválidas.",
            }
        ],
        "manual_tests": ["Probar el flujo principal."],
        "omitted_comments": ["Ninguno."],
    }


def test_render_markdown_with_finding():
    review = reviewer.ReviewResult.model_validate(valid_review_payload())

    markdown = reviewer.render_markdown(review)

    assert "<!-- ai-pr-reviewer -->" in markdown
    assert "## AI Review del PR" in markdown
    assert "### Veredicto" in markdown
    assert "### Resumen" in markdown
    assert "### Cobertura del análisis" in markdown
    assert "- Archivos revisados: src/app.py" in markdown
    assert "- Archivos omitidos: dist/app.js (ignored)" in markdown
    assert "- Diff truncado: No" in markdown
    assert "- Confianza general: **media**" in markdown
    assert "### Cambios principales detectados" in markdown
    assert "### Hallazgos importantes" in markdown
    assert "### Casos que conviene probar manualmente" in markdown
    assert "### Comentarios omitidos" in markdown
    assert "1. **Posible regresión**" in markdown
    assert "Archivo: `src/app.py`" in markdown
    assert "Severidad: **alta**" in markdown
    assert "Categoría: `bug`" in markdown
    assert "Confianza: **media**" in markdown
    assert "Evidencia: La evidencia aparece en el diff." in markdown
    assert "Impacto: Puede romper el flujo de login." in markdown
    assert "Recomendación: Agregar una validación." in markdown
    assert "Test sugerido: Probar login con credenciales inválidas." in markdown


def test_render_markdown_without_findings():
    payload = valid_review_payload()
    payload["findings"] = []
    review = reviewer.ReviewResult.model_validate(payload)

    markdown = reviewer.render_markdown(review)

    assert "### Cobertura del análisis" in markdown
    assert "### Hallazgos importantes" in markdown
    assert "- No se detectaron hallazgos importantes." in markdown


def test_review_result_valid_payload_passes():
    review = reviewer.ReviewResult.model_validate(valid_review_payload())

    assert review.risk == "Medio"
    assert review.confidence == "media"
    assert review.reviewed_files == ["src/app.py"]
    assert review.findings[0].severity == "alta"
    assert review.findings[0].suggested_test


def test_review_result_invalid_risk_fails():
    payload = valid_review_payload()
    payload["risk"] = "Crítico"

    with pytest.raises(pydantic.ValidationError):
        reviewer.ReviewResult.model_validate(payload)


def test_review_result_invalid_severity_fails():
    payload = valid_review_payload()
    payload["findings"][0]["severity"] = "critica"

    with pytest.raises(pydantic.ValidationError):
        reviewer.ReviewResult.model_validate(payload)


def test_review_result_invalid_category_fails():
    payload = valid_review_payload()
    payload["findings"][0]["category"] = "style"

    with pytest.raises(pydantic.ValidationError):
        reviewer.ReviewResult.model_validate(payload)


def test_review_result_invalid_confidence_fails():
    payload = valid_review_payload()
    payload["confidence"] = "segura"

    with pytest.raises(pydantic.ValidationError):
        reviewer.ReviewResult.model_validate(payload)


def test_finding_invalid_confidence_fails():
    payload = valid_review_payload()
    payload["findings"][0]["confidence"] = "segura"

    with pytest.raises(pydantic.ValidationError):
        reviewer.ReviewResult.model_validate(payload)


@pytest.mark.parametrize(
    "field",
    ["reviewed_files", "skipped_files", "diff_truncated", "confidence"],
)
def test_review_result_new_fields_are_required(field):
    payload = valid_review_payload()
    payload.pop(field)

    with pytest.raises(pydantic.ValidationError):
        reviewer.ReviewResult.model_validate(payload)


@pytest.mark.parametrize("field", ["impact", "suggested_test", "confidence"])
def test_finding_new_fields_are_required(field):
    payload = valid_review_payload()
    payload["findings"][0].pop(field)

    with pytest.raises(pydantic.ValidationError):
        reviewer.ReviewResult.model_validate(payload)


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def test_upsert_pr_comment_updates_existing_marker_comment(monkeypatch):
    calls = []
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("PR_NUMBER", "7")

    def fake_github_request(method, url, *, params=None, payload=None):
        calls.append(
            {"method": method, "url": url, "params": params, "payload": payload}
        )
        if method == "GET":
            return FakeResponse([{"id": 123, "body": reviewer.COMMENT_MARKER}])
        return FakeResponse({})

    monkeypatch.setattr(reviewer, "_github_request", fake_github_request)

    reviewer.upsert_pr_comment("updated body")

    assert [call["method"] for call in calls] == ["GET", "PATCH"]
    assert calls[1]["url"].endswith("/issues/comments/123")
    assert calls[1]["payload"] == {"body": "updated body"}


def test_upsert_pr_comment_creates_when_marker_is_absent(monkeypatch):
    calls = []
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("PR_NUMBER", "7")

    def fake_github_request(method, url, *, params=None, payload=None):
        calls.append(
            {"method": method, "url": url, "params": params, "payload": payload}
        )
        if method == "GET":
            return FakeResponse([{"id": 123, "body": "unrelated"}])
        return FakeResponse({})

    monkeypatch.setattr(reviewer, "_github_request", fake_github_request)

    reviewer.upsert_pr_comment("new body")

    assert [call["method"] for call in calls] == ["GET", "POST"]
    assert calls[1]["url"].endswith("/issues/7/comments")
    assert calls[1]["payload"] == {"body": "new body"}
