# Model Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add model validation functionality to settings page, allowing users to verify model configuration availability and features before saving.

**Architecture:** Backend API endpoint performs validation (model existence, API reachability, features, credentials) → Frontend displays validation buttons and status icons for each model field.

**Tech Stack:** FastAPI (backend), React + TypeScript (frontend), Pytest (testing)

---

## File Structure

### Backend Files
- **Modify:** `backend/app/extensions/settings/routers.py` - Add validation endpoint
- **Create:** `backend/app/extensions/settings/validator.py` - Model validation logic
- **Create:** `backend/tests/test_model_validation.py` - Validation tests

### Frontend Files
- **Modify:** `frontend/src/app/settings/basic-settings.tsx` - Add validation buttons and status display

---

## Task 1: Create Model Validator Module

**Files:**
- Create: `backend/app/extensions/settings/validator.py`

- [ ] **Step 1: Write validator module with data models**

```python
"""Model validation logic."""

from typing import Literal
from pydantic import BaseModel

from deerflow.config import get_app_config


class ModelValidationDetails(BaseModel):
    """Validation details for a single model."""

    exists: bool
    api_reachable: bool | None
    supports_thinking: bool
    supports_vision: bool
    has_credentials: bool
    message: str | None
    latency_ms: float | None


class ModelValidationResult(BaseModel):
    """Validation result for a single model."""

    name: str
    status: Literal["available", "unavailable", "error"]
    details: ModelValidationDetails


class ModelValidationRequest(BaseModel):
    """Request to validate models."""

    models: list[str]
```

- [ ] **Step 2: Implement model existence check**

```python
def check_model_exists(model_name: str) -> bool:
    """Check if model exists in configuration."""
    config = get_app_config()
    return any(m.name == model_name for m in config.models)
```

- [ ] **Step 3: Implement API reachability test**

```python
import time
import asyncio
from deerflow.models import create_chat_model


async def test_api_reachable(model_name: str) -> tuple[bool, float | None]:
    """Test if model API is reachable with a lightweight request.

    Returns:
        (reachable, latency_ms)
    """
    try:
        start = time.time()
        model = create_chat_model(model_name, thinking_enabled=False)
        # Send minimal test message
        response = await model.ainvoke([("human", "Hi")])
        latency = (time.time() - start) * 1000
        return True, latency
    except Exception as e:
        return False, None
```

- [ ] **Step 4: Implement feature check**

```python
def get_model_features(model_name: str) -> tuple[bool, bool]:
    """Get model features (thinking, vision support).

    Returns:
        (supports_thinking, supports_vision)
    """
    config = get_app_config()
    model = config.get_model_config(model_name)
    if not model:
        return False, False
    return model.supports_thinking, model.supports_vision
```

- [ ] **Step 5: Implement credentials check**

```python
import os


def check_model_credentials(model_name: str) -> bool:
    """Check if model has required API credentials."""
    config = get_app_config()
    model = config.get_model_config(model_name)
    if not model:
        return False

    # Check if provider-specific env vars are set
    # This is a basic check - real implementation depends on provider
    if "openai" in model.use.lower():
        return bool(os.getenv("OPENAI_API_KEY"))
    elif "anthropic" in model.use.lower() or "claude" in model.use.lower():
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    # Add other providers as needed
    return True  # Default to True for unknown providers
```

- [ ] **Step 6: Implement main validation function**

```python
async def validate_model(model_name: str) -> ModelValidationResult:
    """Validate a single model and return detailed result.

    Args:
        model_name: Name of the model to validate.

    Returns:
        ModelValidationResult with status and details.
    """
    exists = check_model_exists(model_name)

    if not exists:
        return ModelValidationResult(
            name=model_name,
            status="unavailable",
            details=ModelValidationDetails(
                exists=False,
                api_reachable=None,
                supports_thinking=False,
                supports_vision=False,
                has_credentials=False,
                message=f"Model '{model_name}' not found in configuration",
                latency_ms=None,
            ),
        )

    # Run validations in parallel
    has_creds = check_model_credentials(model_name)
    supports_thinking, supports_vision = get_model_features(model_name)
    api_reachable, latency = await test_api_reachable(model_name)

    if api_reachable and has_creds:
        status = "available"
        message = f"Model available (latency: {latency:.0f}ms)"
    else:
        status = "unavailable"
        reasons = []
        if not has_creds:
            reasons.append("missing credentials")
        if not api_reachable:
            reasons.append("API unreachable")
        message = f"Validation failed: {', '.join(reasons)}"

    return ModelValidationResult(
        name=model_name,
        status=status,
        details=ModelValidationDetails(
            exists=True,
            api_reachable=api_reachable,
            supports_thinking=supports_thinking,
            supports_vision=supports_vision,
            has_credentials=has_creds,
            message=message,
            latency_ms=latency,
        ),
    )
```

- [ ] **Step 7: Implement batch validation**

```python
async def validate_models(model_names: list[str]) -> list[ModelValidationResult]:
    """Validate multiple models in parallel.

    Args:
        model_names: List of model names to validate.

    Returns:
        List of ModelValidationResult.
    """
    tasks = [validate_model(name) for name in model_names]
    return await asyncio.gather(*tasks)
```

- [ ] **Step 8: Add to __init__.py**

```python
# In backend/app/extensions/settings/__init__.py
from app.extensions.settings.validator import (
    ModelValidationRequest,
    ModelValidationResult,
    ModelValidationDetails,
    validate_models,
)

__all__ = [
    "ModelValidationRequest",
    "ModelValidationResult",
    "ModelValidationDetails",
    "validate_models",
]
```

- [ ] **Step 9: Commit validator module**

```bash
git add backend/app/extensions/settings/validator.py backend/app/extensions/settings/__init__.py
git commit -m "feat(settings): add model validator module with parallel validation"
```

---

## Task 2: Add Validation API Endpoint

**Files:**
- Modify: `backend/app/extensions/settings/routers.py:44-112`

- [ ] **Step 1: Write failing test for validation endpoint**

```python
# In backend/tests/test_model_validation.py
import pytest
from fastapi.testclient import TestClient
from app.extensions.settings.routers import router


def test_validate_models_empty_list():
    """Test validation with empty model list."""
    client = TestClient(router)
    response = client.post("/api/extensions/models/validate", json={"models": []})
    assert response.status_code == 200
    assert response.json()["results"] == []


def test_validate_models_single_valid():
    """Test validation with a single valid model."""
    client = TestClient(router)
    response = client.post(
        "/api/extensions/models/validate",
        json={"models": ["gpt-4"]},
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["name"] == "gpt-4"
    assert "status" in results[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_model_validation.py -v`
Expected: FAIL with "404 Not Found" or validation error

- [ ] **Step 3: Add validation endpoint to router**

```python
# In backend/app/extensions/settings/routers.py, add after line 112
from app.extensions.settings.validator import (
    ModelValidationRequest,
    ModelValidationResponse,
    validate_models,
)


class ModelValidationResponse(BaseModel):
    """Response model for model validation."""

    results: list[ModelValidationResult]


@router.post("/models/validate", response_model=ModelValidationResponse)
async def validate_models_endpoint(request: ModelValidationRequest) -> ModelValidationResponse:
    """Validate multiple models in parallel.

    Args:
        request: Validation request with list of model names.

    Returns:
        Validation results for each model.

    Example Response:
        ```json
        {
            "results": [
                {
                    "name": "gpt-4",
                    "status": "available",
                    "details": {
                        "exists": true,
                        "api_reachable": true,
                        "supports_thinking": false,
                        "supports_vision": true,
                        "has_credentials": true,
                        "message": "Model available (latency: 523ms)",
                        "latency_ms": 523
                    }
                }
            ]
        }
        ```
    """
    results = await validate_models(request.models)
    return ModelValidationResponse(results=results)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_model_validation.py -v`
Expected: PASS (if model exists in config) or appropriate status

- [ ] **Step 5: Add error handling for empty input**

```python
# In validate_models function in validator.py
async def validate_models(model_names: list[str]) -> list[ModelValidationResult]:
    """Validate multiple models in parallel.

    Args:
        model_names: List of model names to validate.

    Returns:
        List of ModelValidationResult.
    """
    if not model_names:
        return []

    tasks = [validate_model(name) for name in model_names]
    return await asyncio.gather(*tasks)
```

- [ ] **Step 6: Add test for empty list**

```python
# Already added in step 1, just verify it passes
```

- [ ] **Step 7: Run all tests**

Run: `cd backend && pytest tests/test_model_validation.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit validation endpoint**

```bash
git add backend/app/extensions/settings/routers.py backend/tests/test_model_validation.py
git commit -m "feat(settings): add model validation API endpoint"
```

---

## Task 3: Add Frontend Validation Button Component

**Files:**
- Modify: `frontend/src/app/settings/basic-settings.tsx:1-345`

- [ ] **Step 1: Add validation state types**

```typescript
// In basic-settings.tsx, add to interface section
interface ModelValidationRequest {
  models: string[];
}

interface ModelValidationResponse {
  results: ModelValidationResult[];
}

interface ModelValidationResult {
  name: string;
  status: "available" | "unavailable" | "error";
  details: {
    exists: boolean;
    api_reachable: boolean | null;
    supports_thinking: boolean;
    supports_vision: boolean;
    has_credentials: boolean;
    message: string | null;
    latency_ms: number | null;
  };
}
```

- [ ] **Step 2: Add validating model set state**

```typescript
// In BasicSettings component, after line 39
const [validatingModels, setValidatingModels] = useState<Set<string>>(new Set());
```

- [ ] **Step 3: Add validate model function**

```typescript
// In BasicSettings component, after handleSave function
const handleValidateModel = async (modelName: string) => {
  if (validatingModels.has(modelName)) return;

  setValidatingModels((prev) => new Set([...prev, modelName]));
  try {
    const response = await fetch("/api/extensions/models/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ models: [modelName] }),
    });
    if (response.ok) {
      const data = await response.json() as ModelValidationResponse;
      const result = data.results[0];
      if (result) {
        setModelStatuses((prev) => ({
          ...prev,
          [modelName]: {
            status: result.status,
            message: result.details.message,
          },
        }));
      }
    }
  } catch (error) {
    console.error("Failed to validate model:", error);
    setModelStatuses((prev) => ({
      ...prev,
      [modelName]: {
        status: "error",
        message: "Validation failed: network error",
      },
    }));
  } finally {
    setValidatingModels((prev) => {
      const next = new Set(prev);
      next.delete(modelName);
      return next;
    });
  }
};
```

- [ ] **Step 4: Add validation button component (inline)**

```typescript
// In BasicSettings component, before the return statement, add component
function ModelValidateButton({
  modelName,
}: {
  modelName: string;
}) {
  const isValidating = validatingModels.has(modelName);

  return (
    <button
      type="button"
      onClick={() => handleValidateModel(modelName)}
      disabled={isValidating}
      className="ml-2 p-1 hover:bg-accent rounded transition-colors"
      title={isValidating ? "Validating..." : "Validate model"}
    >
      {isValidating ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        <span className="text-sm text-muted-foreground">验证</span>
      )}
    </button>
  );
}
```

- [ ] **Step 5: Add validation button to default_model input**

```typescript
// Find the default_model input div (around line 133-141) and modify
<div className="space-y-2">
  <Label htmlFor="default_model">{t.settings.basic.retrieval.defaultModel}</Label>
  <div className="flex items-center gap-2">
    <Input
      id="default_model"
      value={config.default_model || ""}
      onChange={(e) => handleChange("default_model", e.target.value)}
      placeholder="例如: gpt-4o"
      className="flex-1"
    />
    {config.default_model && (
      <>
        <ModelValidateButton modelName={config.default_model} />
        <span className={getModelStatusColor(config.default_model)}>
          {getModelStatusIcon(config.default_model)}
        </span>
      </>
    )}
  </div>
</div>
```

- [ ] **Step 6: Add validation button to fast_model input**

```typescript
// Find the fast_model input div (around line 142-150) and modify similarly
<div className="space-y-2">
  <Label htmlFor="fast_model">{t.settings.basic.retrieval.fastModel}</Label>
  <div className="flex items-center gap-2">
    <Input
      id="fast_model"
      value={config.fast_model || ""}
      onChange={(e) => handleChange("fast_model", e.target.value)}
      placeholder="用于快速响应的模型"
      className="flex-1"
    />
    {config.fast_model && (
      <>
        <ModelValidateButton modelName={config.fast_model} />
        <span className={getModelStatusColor(config.fast_model)}>
          {getModelStatusIcon(config.fast_model)}
        </span>
      </>
    )}
  </div>
</div>
```

- [ ] **Step 7: Add validation button to content_guard_llm_model input**

```typescript
// Find content_guard_llm_model input (around line 236-242) and modify
<div className="space-y-2">
  <Label htmlFor="content_guard_llm_model">{t.settings.basic.contentGuard.model}</Label>
  <div className="flex items-center gap-2">
    <Input
      id="content_guard_llm_model"
      value={config.content_guard_llm_model || ""}
      onChange={(e) => handleChange("content_guard_llm_model", e.target.value)}
      placeholder={t.settings.basic.contentGuard.modelPlaceholder}
      className="flex-1"
    />
    {config.content_guard_llm_model && (
      <>
        <ModelValidateButton modelName={config.content_guard_llm_model} />
        <span className={getModelStatusColor(config.content_guard_llm_model)}>
          {getModelStatusIcon(config.content_guard_llm_model)}
        </span>
      </>
    )}
  </div>
</div>
```

- [ ] **Step 8: Add i18n entries for validation**

```typescript
// In frontend/src/core/i18n/locales/en-US.ts, add to settings.basic:
basic: {
  // ... existing keys
  validateModel: "Validate",
  validating: "Validating...",
  validation: {
    available: "Available",
    unavailable: "Unavailable",
    error: "Error",
    message: "Validation message",
  },
}
```

```typescript
// In frontend/src/core/i18n/locales/zh-CN.ts:
basic: {
  // ... existing keys
  validateModel: "验证",
  validating: "验证中...",
  validation: {
    available: "可用",
    unavailable: "不可用",
    error: "错误",
    message: "验证信息",
  },
}
```

- [ ] **Step 9: Update ModelValidateButton to use i18n**

```typescript
// Update the ModelValidateButton component
function ModelValidateButton({
  modelName,
}: {
  modelName: string;
}) {
  const isValidating = validatingModels.has(modelName);

  return (
    <button
      type="button"
      onClick={() => handleValidateModel(modelName)}
      disabled={isValidating}
      className="ml-2 p-1 hover:bg-accent rounded transition-colors"
      title={isValidating ? t.settings.basic.validating : t.settings.basic.validateModel}
    >
      {isValidating ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        <span className="text-sm text-muted-foreground">{t.settings.basic.validateModel}</span>
      )}
    </button>
  );
}
```

- [ ] **Step 10: Update status message display**

```typescript
// Add tooltip for status icon
<span
  className={getModelStatusColor(modelName)}
  title={modelStatuses[modelName]?.message || ""}
>
  {getModelStatusIcon(modelName)}
</span>
```

- [ ] **Step 11: Type check**

Run: `cd frontend && pnpm typecheck`
Expected: No type errors

- [ ] **Step 12: Lint check**

Run: `cd frontend && pnpm lint`
Expected: No lint errors

- [ ] **Step 13: Commit frontend changes**

```bash
git add frontend/src/app/settings/basic-settings.tsx frontend/src/core/i18n/locales/en-US.ts frontend/src/core/i18n/locales/zh-CN.ts
git commit -m "feat(settings): add model validation buttons and status display"
```

---

## Task 4: Update Types for Model Status

**Files:**
- Modify: `frontend/src/app/settings/basic-settings.tsx:26-30`

- [ ] **Step 1: Update ModelChoice interface**

```typescript
// Update ModelChoice to include validation status
interface ModelChoice {
  name: string;
  status?: "available" | "unavailable" | "error";
  message?: string;
  // Keep existing fields
}
```

- [ ] **Step 2: Commit interface update**

```bash
git add frontend/src/app/settings/basic-settings.tsx
git commit -m "fix(settings): update ModelChoice interface for validation status"
```

---

## Task 5: Test Integration End-to-End

**Files:**
- Test: `frontend and backend integration`

- [ ] **Step 1: Start all services**

Run: `make dev`
Expected: All services running, frontend accessible at http://localhost:2026

- [ ] **Step 2: Navigate to settings page**

Action: Open browser to http://localhost:2026/settings
Expected: Settings page loads successfully

- [ ] **Step 3: Enter a model name**

Action: Type "gpt-4" in default_model field
Expected: Field shows the input value

- [ ] **Step 4: Click validation button**

Action: Click the "验证" button next to the model field
Expected:
- Button shows loading spinner
- After a few seconds, status icon appears
- If model is configured and accessible: green ✓
- If model is not configured: red ✗

- [ ] **Step 5: Test invalid model**

Action: Type "invalid-model-name" and validate
Expected: Status shows red ✗ with error message

- [ ] **Step 6: Test multiple validations**

Action: Validate default_model, fast_model, content_guard_llm_model
Expected:
- Can validate multiple models independently
- Each validation shows correct status

- [ ] **Step 7: Test save functionality**

Action: Click "保存更改" button after some validations failed
Expected:
- Save proceeds (only warning, not blocking)
- Toast shows success message

- [ ] **Step 8: Stop services**

Run: `make stop`
Expected: All services stopped

- [ ] **Step 9: Document any issues found**

If issues found during testing, create tasks to fix them.

---

## Task 6: Add Documentation

**Files:**
- Modify: `backend/docs/API.md` or create new docs

- [ ] **Step 1: Add validation endpoint documentation**

```markdown
# Model Validation

## POST /api/extensions/models/validate

Validate multiple models in parallel.

### Request Body

```json
{
  "models": ["gpt-4", "claude-3-opus"]
}
```

### Response

```json
{
  "results": [
    {
      "name": "gpt-4",
      "status": "available",
      "details": {
        "exists": true,
        "api_reachable": true,
        "supports_thinking": false,
        "supports_vision": true,
        "has_credentials": true,
        "message": "Model available (latency: 523ms)",
        "latency_ms": 523
      }
    }
  ]
}
```

### Status Values

- `available`: Model is configured and API is reachable
- `unavailable`: Model exists but has issues (missing credentials, API unreachable)
- `error`: Model not found in configuration
```

- [ ] **Step 2: Commit documentation**

```bash
git add backend/docs/API.md
git commit -m "docs: add model validation API documentation"
```

---

## Task 7: Cleanup and Optimization

**Files:**
- Modify: Various files for optimization

- [ ] **Step 1: Add validation caching (optional)**

```python
# In validator.py, add simple cache
from functools import lru_cache
import time


@lru_cache(maxsize=100)
def _get_model_config_cached(model_name: str):
    """Cached model config lookup."""
    return get_app_config().get_model_config(model_name)
```

- [ ] **Step 2: Add debouncing for validation (frontend)**

```typescript
// Add debounce utility or use existing one
import { useDebounce } from "@/hooks/use-debounce";  // Create if needed
```

- [ ] **Step 3: Run all tests**

Run: `make test`
Expected: All tests pass

- [ ] **Step 4: Commit optimizations**

```bash
git add backend/app/extensions/settings/validator.py
git commit -m "perf(settings): add model config caching for validation"
```

---

## Final Verification

- [ ] **Step 1: Run full test suite**

Run: `make test`
Expected: All backend and frontend tests pass

- [ ] **Step 2: Type check**

Run: `cd frontend && pnpm typecheck`
Expected: No type errors

- [ ] **Step 3: Lint**

Run: `make lint`
Expected: No lint errors

- [ ] **Step 4: Build production**

Run: `cd frontend && pnpm build`
Expected: Build succeeds without errors

- [ ] **Step 5: Final commit**

```bash
git add .
git commit -m "feat(settings): complete model validation feature implementation"
```
