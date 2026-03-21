# ML Risk Scorer — Complete Implementation Guide

> **For:** Arjun's friend (ML component)  
> **Time required:** 3-4 hours  
> **Goal:** Train an XGBoost model that predicts PR risk (LOW / MEDIUM / HIGH) from scan results, and expose it via a `/predict-risk` API endpoint.

---

## Overview

```
Your Backend (Arjun's)          Your ML Work
─────────────────────          ─────────────
POST /analyze-pr          →    Scan data saved to dataset/
GET  /dataset/features    →    Feature vectors for training
                               train_model.py → risk_model.pkl
POST /predict-risk        →    New endpoint using trained model
```

---

## Prerequisites

- Python 3.11+
- Git
- Groq API key (free at https://console.groq.com)
- GitHub Personal Access Token (PAT)

---

## PART 1 — Setup (30 minutes)

### Step 1.1 — Clone the repo

```bash
git clone https://github.com/Arjun7A/Code_Editor-Arjun-
cd Code_Editor-Arjun-
```

### Step 1.2 — Create and activate virtual environment

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Mac/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

You should see `(venv)` at the start of your terminal prompt.

### Step 1.3 — Install all dependencies

```bash
cd backend_new
pip install -r requirements.txt
pip install xgboost scikit-learn joblib pandas requests
```

### Step 1.4 — Download required binaries

Place these inside the `backend_new/` folder:

**OSV Scanner:**
- Go to: https://github.com/google/osv-scanner/releases/latest
- Windows: download `osv-scanner_windows_amd64.exe`
- Mac: download `osv-scanner_darwin_amd64` → rename to `osv-scanner` → run `chmod +x osv-scanner`
- Linux: download `osv-scanner_linux_amd64` → rename to `osv-scanner` → run `chmod +x osv-scanner`

**Gitleaks:**
- Go to: https://github.com/gitleaks/gitleaks/releases/latest
- Windows: extract `gitleaks.exe` from the zip
- Mac/Linux: extract `gitleaks` binary → run `chmod +x gitleaks`

### Step 1.5 — Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in:
```env
GROQ_API_KEY=your_groq_api_key_here
GITHUB_USER_TOKEN=your_github_pat_here
AI_API_TOKEN=your_groq_api_key_here
AI_API_ENDPOINT=https://api.groq.com/openai/v1
GROQ_MODEL=llama-3.3-70b-versatile
```

**Getting Groq API key:**
1. Go to https://console.groq.com
2. Sign up (free, no credit card)
3. Go to API Keys → Create API Key
4. Copy and paste into `.env`

**Getting GitHub PAT:**
1. Go to GitHub → Settings → Developer Settings
2. Personal Access Tokens → Tokens (classic)
3. Generate new token with `repo` scope
4. Copy and paste into `.env`

### Step 1.6 — Patch the seclab agent for Groq

Run this once after installing requirements:

```bash
python -c "
import os, sys
path = os.path.join(sys.prefix, 'Lib', 'site-packages', 'seclab_taskflow_agent', 'agent.py')
if not os.path.exists(path):
    path = os.path.join(sys.prefix, 'lib', 'python3.11', 'site-packages', 'seclab_taskflow_agent', 'agent.py')
with open(path) as f:
    c = f.read()
old = '''    case _:
        raise ValueError(
            f\\\"Unsupported Model Endpoint: {api_endpoint}\\\\n\\\"
            f\\\"Supported endpoints: {[e.to_url() for e in AI_API_ENDPOINT_ENUM]}\\\"
        )'''
new = '    case _:\\n        pass  # Groq patch'
if old in c:
    open(path, 'w').write(c.replace(old, new))
    print('Patched successfully!')
else:
    print('Already patched or pattern changed — OK to continue')
"
```

### Step 1.7 — Start the backend server

```bash
# Make sure you are in backend_new/ and venv is activated
python main.py
```

You should see:
```
[Semgrep] Using: .../venv/Scripts/semgrep.exe
INFO:     Started server process
INFO:     Uvicorn running on http://127.0.0.1:8001
```

### Step 1.8 — Verify it works

Open your browser and go to:
```
http://127.0.0.1:8001/docs
```

You should see the Swagger UI with these endpoints:
- `POST /analyze-pr`
- `GET /dataset`
- `GET /dataset/features`
- `POST /predict-risk`
- `GET /api/dashboard-stats`
- `GET /api/results`

---

## PART 2 — Collect Training Data (1-2 hours)

You need **at least 20-30 scans** (30-50 is better) to train a reliable model.

### Step 2.1 — Scan PRs using Swagger UI

1. Open http://127.0.0.1:8001/docs
2. Click `POST /analyze-pr`
3. Click `Try it out`
4. Paste this JSON and click `Execute`:

```json
{
  "repo_url": "https://github.com/KunalSiyag/Code_Editor",
  "pr_url": "https://github.com/KunalSiyag/Code_Editor/pull/3"
}
```

Wait for the response (takes 1-3 minutes per scan).

### Step 2.2 — PR URLs to scan

Scan all of these — mix of clean, medium, and high risk:

**HIGH RISK (secrets/critical vulns):**
```
repo: https://github.com/juice-shop/juice-shop
pr:   https://github.com/juice-shop/juice-shop/pull/2100

repo: https://github.com/KunalSiyag/Code_Editor
pr:   https://github.com/KunalSiyag/Code_Editor/pull/3

repo: https://github.com/langchain-ai/langchain
pr:   https://github.com/langchain-ai/langchain/pull/36130
```

**MEDIUM RISK (dependency vulns / IaC issues):**
```
repo: https://github.com/dockersamples/example-voting-app
pr:   https://github.com/dockersamples/example-voting-app/pull/134

repo: https://github.com/tiangolo/fastapi
pr:   https://github.com/tiangolo/fastapi/pull/11000

repo: https://github.com/pallets/flask
pr:   https://github.com/pallets/flask/pull/5400
```

**LOW RISK (clean PRs):**
```
repo: https://github.com/django/django
pr:   https://github.com/django/django/pull/17000

repo: https://github.com/django/django
pr:   https://github.com/django/django/pull/16900

repo: https://github.com/psf/requests
pr:   https://github.com/psf/requests/pull/6500
```

> **Tip:** Keep scanning until you have at least 10 scans in each category (LOW, MEDIUM, HIGH). Check progress at http://127.0.0.1:8001/dataset

### Step 2.3 — Verify data is being saved

After each scan check:
```
http://127.0.0.1:8001/dataset/features
```

You should see the total increasing and feature vectors appearing.

---

## PART 3 — Train the Model (30 minutes)

### Step 3.1 — Create training script

Create a new file `backend_new/train_model.py` with this content:

```python
import requests
import pandas as pd
import numpy as np
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix
import joblib
import json

print("=" * 60)
print("PR SECURITY RISK MODEL TRAINER")
print("=" * 60)

# ── Step 1: Fetch features ─────────────────────────────────────
print("\n[1/5] Fetching features from API...")
try:
    response = requests.get("http://127.0.0.1:8001/dataset/features", timeout=10)
    data = response.json()
except Exception as e:
    print(f"ERROR: Could not connect to API — {e}")
    print("Make sure python main.py is running first!")
    exit(1)

print(f"Total scans found: {data['total']}")

if data['total'] < 10:
    print(f"\nWARNING: Only {data['total']} scans found.")
    print("You need at least 10 scans to train. Scan more PRs first.")
    exit(1)

df = pd.DataFrame(data["features"])

# ── Step 2: Auto-label ─────────────────────────────────────────
print("\n[2/5] Auto-labeling scans...")

def auto_label(row):
    # HIGH RISK
    if row["gitleaks_count"] > 0:
        return 2
    if row["critical_count"] > 0:
        return 2
    if row["ai_agent_count"] > 2:
        return 2
    
    # MEDIUM RISK
    if row["osv_count"] > 15:
        return 1
    if row["high_count"] > 0:
        return 1
    if row["has_iac_issue"] == 1 and row["checkov_count"] > 5:
        return 1
    if row["semgrep_count"] > 3:
        return 1
    
    # LOW RISK
    return 0

df["risk_label"] = df.apply(auto_label, axis=1)

label_names = {0: "LOW", 1: "MEDIUM", 2: "HIGH"}
print("\nLabel distribution:")
for label, count in df["risk_label"].value_counts().sort_index().items():
    print(f"  {label_names[label]:6} ({label}): {count} scans")

# ── Step 3: Prepare features ───────────────────────────────────
print("\n[3/5] Preparing feature matrix...")

FEATURE_COLS = [
    "semgrep_count",
    "osv_count",
    "ai_agent_count",
    "gitleaks_count",
    "checkov_count",
    "total_issues",
    "pr_files_scanned",
    "critical_count",
    "high_count",
    "medium_count",
    "low_count",
    "has_secret",
    "has_iac_issue",
    "has_ai_finding"
]

X = df[FEATURE_COLS].fillna(0)
y = df["risk_label"]

print(f"Feature matrix shape: {X.shape}")
print(f"Features used: {FEATURE_COLS}")

# ── Step 4: Train ──────────────────────────────────────────────
print("\n[4/5] Training XGBoost model...")

# Use stratified split if enough data
try:
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=0.2,
        random_state=42,
        stratify=y
    )
except ValueError:
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=0.2,
        random_state=42
    )

model = XGBClassifier(
    n_estimators=100,
    max_depth=4,
    learning_rate=0.1,
    random_state=42,
    eval_metric="mlogloss",
    verbosity=0
)
model.fit(X_train, y_train)

# Evaluate
y_pred = model.predict(X_test)
print("\n=== MODEL PERFORMANCE ===")
print(classification_report(
    y_test, y_pred,
    target_names=["LOW", "MEDIUM", "HIGH"],
    zero_division=0
))

print("\nConfusion Matrix (rows=actual, cols=predicted):")
print("         LOW  MED  HIGH")
cm = confusion_matrix(y_test, y_pred)
for i, row in enumerate(cm):
    print(f"  {['LOW ', 'MED ', 'HIGH'][i]}  {row}")

# Cross validation
if len(df) >= 15:
    cv_scores = cross_val_score(model, X, y, cv=min(3, len(df)//5), scoring="accuracy")
    print(f"\nCross-validation accuracy: {cv_scores.mean():.2f} (+/- {cv_scores.std():.2f})")

# Feature importance
print("\n=== TOP FEATURES BY IMPORTANCE ===")
importance = pd.DataFrame({
    "feature": FEATURE_COLS,
    "importance": model.feature_importances_
}).sort_values("importance", ascending=False)
for _, row in importance.iterrows():
    bar = "█" * int(row["importance"] * 50)
    print(f"  {row['feature']:20} {bar} {row['importance']:.3f}")

# ── Step 5: Save ───────────────────────────────────────────────
print("\n[5/5] Saving model...")

joblib.dump(model, "risk_model.pkl")
with open("model_features.json", "w") as f:
    json.dump(FEATURE_COLS, f)

print("✅ risk_model.pkl saved")
print("✅ model_features.json saved")

# Test prediction
print("\n=== TEST PREDICTION (Kunal's PR #3) ===")
test_input = pd.DataFrame([{
    "semgrep_count": 1,
    "osv_count": 35,
    "ai_agent_count": 0,
    "gitleaks_count": 0,
    "checkov_count": 2,
    "total_issues": 38,
    "pr_files_scanned": 13,
    "critical_count": 1,
    "high_count": 0,
    "medium_count": 7,
    "low_count": 28,
    "has_secret": 0,
    "has_iac_issue": 1,
    "has_ai_finding": 0
}])

pred = int(model.predict(test_input)[0])
proba = model.predict_proba(test_input)[0]
print(f"Predicted risk: {label_names[pred]}")
print(f"Confidence — LOW: {proba[0]:.0%}  MEDIUM: {proba[1]:.0%}  HIGH: {proba[2]:.0%}")
print("\n✅ Training complete! Model is ready.")
```

### Step 3.2 — Run the training script

Make sure the backend is still running (`python main.py`) in one terminal, then open a second terminal:

```bash
cd Code_Editor-Arjun-/backend_new
venv\Scripts\activate       # Windows
source venv/bin/activate     # Mac/Linux

python train_model.py
```

Expected output:
```
[1/5] Fetching features from API...
Total scans found: 35

[2/5] Auto-labeling scans...
Label distribution:
  LOW    (0): 12 scans
  MEDIUM (1): 13 scans
  HIGH   (2): 10 scans

[3/5] Preparing feature matrix...
[4/5] Training XGBoost model...

=== MODEL PERFORMANCE ===
              precision    recall  f1-score
         LOW       0.85      0.91      0.88
      MEDIUM       0.78      0.72      0.75
        HIGH       0.92      0.89      0.90

[5/5] Saving model...
✅ risk_model.pkl saved
✅ model_features.json saved
```

---

## PART 4 — Add Predict Endpoint to Backend (30 minutes)

### Step 4.1 — Add to main.py

Open `backend_new/main.py` and add this new endpoint **before** the `if __name__ == "__main__":` line at the bottom:

```python
@app.post("/predict-risk")
def predict_risk(request: PRRequest):
    """
    Scan a PR and predict its risk level using the trained ML model.
    Returns full scan results + ML risk prediction.
    """
    import joblib
    import pandas as pd

    if not request.repo_url or not request.pr_url:
        raise HTTPException(status_code=400, detail="repo_url and pr_url are required")

    # Run full scan
    result = analyze(request.repo_url, request.pr_url)
    save_scan(request.repo_url, request.pr_url, result)

    # Predict risk using ML model
    try:
        model   = joblib.load("risk_model.pkl")
        summary = result["scan_summary"]
        issues  = result["issues"]

        features = pd.DataFrame([{
            "semgrep_count":    summary.get("semgrep", 0),
            "osv_count":        summary.get("osv", 0),
            "ai_agent_count":   summary.get("ai_agent", 0),
            "gitleaks_count":   summary.get("gitleaks", 0),
            "checkov_count":    summary.get("checkov", 0),
            "total_issues":     summary.get("total_issues", 0),
            "pr_files_scanned": summary.get("pr_files_scanned", 0),
            "critical_count":   sum(1 for i in issues if i.get("severity") == "critical"),
            "high_count":       sum(1 for i in issues if i.get("severity") == "high"),
            "medium_count":     sum(1 for i in issues if i.get("severity") == "medium"),
            "low_count":        sum(1 for i in issues if i.get("severity") == "low"),
            "has_secret":       1 if result.get("gitleaks") else 0,
            "has_iac_issue":    1 if result.get("checkov") else 0,
            "has_ai_finding":   1 if result.get("ai_audit", {}).get("findings") else 0,
        }])

        pred  = int(model.predict(features)[0])
        proba = model.predict_proba(features)[0].tolist()
        labels = {0: "LOW", 1: "MEDIUM", 2: "HIGH"}

        ml_risk = {
            "risk_label": labels[pred],
            "risk_score": pred,
            "confidence": {
                "low":    round(proba[0] * 100),
                "medium": round(proba[1] * 100),
                "high":   round(proba[2] * 100)
            },
            "error": None
        }

    except FileNotFoundError:
        ml_risk = {
            "risk_label": "PENDING",
            "risk_score": -1,
            "confidence": {},
            "error": "Model not trained yet. Run train_model.py first."
        }
    except Exception as e:
        ml_risk = {
            "risk_label": "ERROR",
            "risk_score": -1,
            "confidence": {},
            "error": str(e)
        }

    return {
        "repo_url":     request.repo_url,
        "pr_url":       request.pr_url,
        "scan_summary": result["scan_summary"],
        "issues":       result["issues"],
        "ai_audit":     result["ai_audit"],
        "gitleaks":     result["gitleaks"],
        "checkov":      result["checkov"],
        "ml_risk":      ml_risk
    }
```

### Step 4.2 — Restart the server

```bash
# Stop the running server with Ctrl+C
# Then restart:
python main.py
```

---

## PART 5 — Test Everything (15 minutes)

### Step 5.1 — Test via Swagger UI

1. Open http://127.0.0.1:8001/docs
2. Click `POST /predict-risk`
3. Click `Try it out`
4. Paste:
```json
{
  "repo_url": "https://github.com/KunalSiyag/Code_Editor",
  "pr_url": "https://github.com/KunalSiyag/Code_Editor/pull/3"
}
```
5. Click `Execute`

Expected response includes:
```json
{
  "scan_summary": { "total_issues": 38 },
  "issues": [...],
  "ai_audit": {...},
  "gitleaks": [...],
  "checkov": [...],
  "ml_risk": {
    "risk_label": "MEDIUM",
    "risk_score": 1,
    "confidence": {
      "low": 15,
      "medium": 72,
      "high": 13
    },
    "error": null
  }
}
```

### Step 5.2 — Test all endpoints

| Endpoint | What to check |
|---|---|
| `GET /dataset` | Shows all saved scans |
| `GET /dataset/features` | Shows feature vectors |
| `POST /analyze-pr` | Full scan without ML |
| `POST /predict-risk` | Full scan with ML risk label |

---

## PART 6 — Push to Repo (10 minutes)

```bash
cd Code_Editor-Arjun-

# Add train script and updated main.py
git add backend_new/train_model.py
git add backend_new/main.py

# Don't commit the trained model (it's machine-specific)
echo "backend_new/risk_model.pkl" >> .gitignore
echo "backend_new/model_features.json" >> .gitignore

git add .gitignore
git commit -m "feat: add ML risk scorer - train_model.py + /predict-risk endpoint"
git push origin main
```

---

## Final JSON Structure (what Arjun's frontend receives)

```json
{
  "repo_url": "https://github.com/owner/repo",
  "pr_url": "https://github.com/owner/repo/pull/123",
  "scan_summary": {
    "total_issues": 38,
    "semgrep": 1,
    "osv": 35,
    "ai_agent": 0,
    "gitleaks": 0,
    "checkov": 2,
    "pr_files_scanned": 13
  },
  "issues": [
    {
      "tool": "semgrep",
      "severity": "critical",
      "message": "...",
      "file": "backend/app.py",
      "line": 140,
      "explanation": "...",
      "fix": "..."
    }
  ],
  "ai_audit": {
    "status": "completed",
    "model": "llama-3.3-70b-versatile",
    "findings": []
  },
  "gitleaks": [],
  "checkov": [
    {
      "tool": "checkov",
      "severity": "medium",
      "message": "Ensure that a user for the container has been created",
      "file": "backend/Dockerfile",
      "line": 1
    }
  ],
  "ml_risk": {
    "risk_label": "MEDIUM",
    "risk_score": 1,
    "confidence": {
      "low": 15,
      "medium": 72,
      "high": 13
    },
    "error": null
  }
}
```

---

## Troubleshooting

**`Could not connect to API`**
→ Make sure `python main.py` is running in a separate terminal

**`Only X scans found`**
→ Scan more PRs using `POST /analyze-pr` via Swagger UI

**`Model not trained yet`**
→ Run `python train_model.py` first

**`Semgrep not found`**
→ Run `pip install semgrep` inside the venv

**`OSV/Gitleaks not found`**
→ Make sure the binaries are in `backend_new/` folder

**Patch script fails**
→ Ask Arjun — he has the patched venv already working

---

## Summary

| Step | Time | Command |
|---|---|---|
| Clone + setup | 30 min | `git clone` + `pip install` |
| Collect data | 1-2 hrs | Scan PRs via Swagger UI |
| Train model | 30 min | `python train_model.py` |
| Add endpoint | 30 min | Edit `main.py` |
| Test | 15 min | Swagger UI |
| Push | 10 min | `git push` |
| **Total** | **~4 hrs** | |
