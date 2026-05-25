# PR Risk Reviewer

[![AI PR Review](https://github.com/NahimMora/pr-risk-reviewer/actions/workflows/ai-pr-review.yml/badge.svg)](https://github.com/NahimMora/pr-risk-reviewer/actions/workflows/ai-pr-review.yml)

**PR Risk Reviewer** is a GitHub Actions bot that reviews Pull Requests with OpenAI and posts a structured risk summary directly in the PR conversation.

It is designed to act as a focused pre-merge assistant: it reads the PR diff, detects probable bugs, missing tests, regressions, edge cases, architecture issues, and concrete security risks, then publishes a concise review comment.

The goal is not to replace human code review. The goal is to catch risk signals early and make PR review faster, clearer, and more consistent.

---

## What it does

PR Risk Reviewer:

- Runs automatically on Pull Request events.
- Reads changed files through the GitHub API.
- Builds a compact diff payload.
- Sends the diff to the OpenAI Responses API.
- Uses Structured Outputs with a strict JSON Schema.
- Validates the model response with Pydantic.
- Posts or updates a single structured PR comment.
- Avoids noisy subjective style feedback.
- Focuses on actionable findings backed by visible diff evidence.

Example focus areas:

- probable bugs;
- regressions;
- missing tests;
- edge cases;
- architecture inconsistencies;
- concrete security risks;
- unhandled errors;
- risky behavioral changes.

---

## What it does not do

PR Risk Reviewer intentionally does **not**:

- replace human review;
- execute code from the PR;
- use `pull_request_target`;
- post inline comments yet;
- review subjective style by default;
- run on fork PRs that require secrets;
- claim full repository understanding;
- guarantee correctness of LLM output.

It is a risk assistant, not an approval system.

---

## Architecture

```text
Pull Request
  ↓
GitHub Actions
  ↓
Python reviewer script
  ↓
GitHub API: PR files + diff
  ↓
OpenAI Responses API
  ↓
Structured Outputs JSON Schema
  ↓
Pydantic validation
  ↓
Markdown rendering
  ↓
Create or update PR comment
```

The workflow checks out the **base branch** instead of the PR branch. This is intentional: the reviewer runs trusted code already present in the base branch, while the actual PR changes are read through the GitHub API.

---

## Example output

```md
## AI Review del PR

### Veredicto
Riesgo: Medio

### Resumen
Se agregó una función login que decodifica un token para obtener un user_id y lo retorna. No hay manejo de errores ni validaciones visibles, lo que puede provocar fallos o comportamientos inesperados si el token es inválido o malformado.

### Cobertura del análisis
- Archivos revisados: app/auth.py
- Archivos omitidos: Ninguno
- Diff truncado: No
- Confianza general: media

### Cambios principales detectados
- Se añadió la función login que recibe un token, decodifica el user_id y lo devuelve en un diccionario.

### Hallazgos importantes

1. **Ausencia de manejo de errores en la función login**

   Archivo: `app/auth.py`  
   Severidad: **media**  
   Categoría: `bug`  
   Confianza: **media**

   Evidencia: La función login llama a decode_token(token) sin manejo de excepciones o validaciones adicionales.

   Impacto: Si decode_token falla por un token inválido o malformado, login podría lanzar una excepción no controlada o devolver resultados inesperados.

   Recomendación: Agregar manejo de excepciones para capturar posibles errores al decodificar el token e implementar validaciones para tokens inválidos o nulos.

   Test sugerido: Probar la función login con tokens válidos, nulos, vacíos y malformados.

### Casos que conviene probar manualmente
- Llamar a login con un token válido.
- Llamar a login con un token inválido.
- Probar token vacío o nulo.

### Comentarios omitidos
- No se comentaron temas de estilo menor.
```

---

## Repository structure

```text
.
├── .github/
│   └── workflows/
│       └── ai-pr-review.yml
├── docs/
│   ├── architecture.md
│   └── example-output.md
├── scripts/
│   └── ai_pr_review.py
├── tests/
│   └── test_ai_pr_review.py
├── .ai-reviewer.yml
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Add the OpenAI API key

In your GitHub repository:

```text
Settings → Secrets and variables → Actions → Secrets
```

Create a secret:

```text
OPENAI_API_KEY
```

### 2. Add the OpenAI model

In:

```text
Settings → Secrets and variables → Actions → Variables
```

Create a variable:

```text
OPENAI_MODEL
```

Recommended default:

```text
gpt-4.1-mini
```

### 3. Enable workflow write permissions

In:

```text
Settings → Actions → General → Workflow permissions
```

Select:

```text
Read and write permissions
```

The workflow also declares explicit permissions:

```yaml
permissions:
  contents: read
  pull-requests: write
  issues: write
```

These are required because the bot reads PR data and creates or updates a comment in the PR conversation.

---

## GitHub Actions workflow

The bot runs on Pull Request events:

```yaml
on:
  pull_request:
    types:
      - opened
      - synchronize
      - reopened
      - ready_for_review
```

It does not run on draft PRs or fork PRs:

```yaml
if: >
  github.event.pull_request.draft == false &&
  github.event.pull_request.head.repo.fork == false
```

This is intentional because repository secrets are not available to forked Pull Requests.

---

## Configuration

The bot is configured through `.ai-reviewer.yml`.

Example:

```yaml
review:
  mode: summary
  max_files: 25
  max_diff_chars: 60000
  min_severity: media

ignore:
  - "package-lock.json"
  - "pnpm-lock.yaml"
  - "yarn.lock"
  - "dist/**"
  - "build/**"
  - "node_modules/**"
  - "*.png"
  - "*.jpg"
  - "*.jpeg"
  - "*.svg"
  - "*.pdf"

focus:
  - bugs
  - security
  - regressions
  - missing_tests
  - edge_cases
  - architecture

bot:
  marker: "<!-- ai-pr-reviewer -->"
```

### Main options

| Option | Description |
|---|---|
| `review.max_files` | Maximum number of changed files to include in the review payload. |
| `review.max_diff_chars` | Maximum diff size sent to the model. |
| `review.min_severity` | Minimum severity expected from the review. |
| `ignore` | Glob patterns for files that should not be reviewed. |
| `focus` | Review categories the model should prioritize. |
| `bot.marker` | Hidden marker used to update the previous bot comment instead of creating duplicates. |

---

## Local development

Install dependencies:

```bash
pip install -r requirements.txt
```

Run tests:

```bash
python -m pytest
```

Validate Python syntax:

```bash
python -m py_compile scripts/ai_pr_review.py
```

Run local mock mode:

```bash
python scripts/ai_pr_review.py --local-mock
```

The local mock mode does not call GitHub or OpenAI. It only renders a sample review comment so the Markdown output can be inspected safely.

---

## Environment variables

The normal runtime expects:

| Variable | Purpose |
|---|---|
| `GITHUB_TOKEN` | Token used to call the GitHub API. |
| `GITHUB_REPOSITORY` | Repository name in `owner/repo` format. |
| `PR_NUMBER` | Pull Request number being reviewed. |
| `OPENAI_API_KEY` | API key used to call OpenAI. |
| `OPENAI_MODEL` | Model used for the review. |

In GitHub Actions, these are injected by the workflow.

---

## Security model

PR Risk Reviewer is designed to avoid executing untrusted PR code.

Security decisions:

- It does **not** use `pull_request_target`.
- It checks out the base branch, not the PR branch.
- It reads PR changes through the GitHub API.
- It skips fork PRs because secrets are not available safely.
- It uses minimal GitHub token permissions.
- It posts one summary comment instead of modifying code or running arbitrary commands from the PR.

Important privacy note:

The PR diff is sent to OpenAI for analysis. Do not use this bot on repositories where sending code diffs to a third-party model provider is not allowed.

---

## Structured output

The OpenAI response is constrained with a JSON Schema and validated with Pydantic before being rendered.

The review model includes:

- risk;
- summary;
- reviewed files;
- skipped files;
- diff truncation status;
- confidence;
- main changes;
- findings;
- manual tests;
- omitted comments.

Each finding includes:

- title;
- file;
- severity;
- category;
- confidence;
- evidence;
- impact;
- recommendation;
- suggested test.

This avoids free-form, hard-to-parse model output.

---

## Current limitations

PR Risk Reviewer is intentionally conservative in its first version.

Current limitations:

- It only reviews the PR diff.
- It does not yet read broader repository context.
- Large diffs may be truncated.
- It does not post inline comments.
- It does not create GitHub Check annotations.
- It does not replace human review.
- The LLM can still make incorrect or incomplete observations.
- It does not currently run on fork PRs requiring secrets.

---

## Roadmap

Planned improvements:

- Context files from the base branch.
- Optional repository architecture awareness.
- Severity thresholds for posting comments.
- Inline comments on specific diff lines.
- Better deduplication across review runs.
- SARIF or GitHub Check annotations.
- GitHub App mode.
- Multi-provider LLM support.
- Cost controls and token usage reporting.
- Configurable language and tone.

---

## Development workflow

Recommended workflow:

```bash
git checkout main
git pull
git checkout -b feature/my-change
```

Make changes, then:

```bash
git add .
git commit -m "feat: describe change"
git push -u origin feature/my-change
```

Open a Pull Request.

The bot will run automatically and post or update its review comment.

---

## Why a single PR comment?

The MVP uses one summary comment instead of inline comments because it is:

- less noisy;
- easier to deduplicate;
- safer to implement;
- easier to audit;
- more useful for high-level risk review.

Inline comments are planned for a later version, after the summary reviewer is consistently accurate.

---

## License

No license has been selected yet.
