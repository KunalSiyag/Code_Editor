from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from analyzer import analyze

app = FastAPI(title="PR Security Scanner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PRRequest(BaseModel):
    repo_url: str
    pr_url:   str


@app.get("/")
def home():
    return {"message": "PR Security Scanner Running"}


@app.post("/analyze-pr")
def analyze_pr(request: PRRequest):
    if not request.repo_url or not request.pr_url:
        raise HTTPException(status_code=400, detail="repo_url and pr_url are required")

    result = analyze(request.repo_url, request.pr_url)

    return {
        "repo_url":     request.repo_url,
        "pr_url":       request.pr_url,
        "scan_summary": result["scan_summary"],
        "issues":       result["issues"],        # Semgrep + OSV
        "ai_audit":     result["ai_audit"],      # AI Agent
        "gitleaks":     result["gitleaks"],      # Secret scanning
        "checkov":      result["checkov"],       # IaC misconfigurations
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)