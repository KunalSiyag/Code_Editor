import subprocess
import json
import os
import re
import time
import shutil as _shutil
import sys as _sys

from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────────
_groq_key  = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_CLIENT = Groq(api_key=_groq_key)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ══════════════════════════════════════════════════════════════════════════════
# GITLEAKS
# ══════════════════════════════════════════════════════════════════════════════
def _find_gitleaks() -> str:
    """Auto-detect gitleaks binary."""
    env_path = os.getenv("GITLEAKS_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    local = os.path.join(BASE_DIR, "gitleaks.exe" if os.name == "nt" else "gitleaks")
    if os.path.exists(local):
        return local
    found = _shutil.which("gitleaks")
    if found:
        return found
    raise FileNotFoundError(
        "gitleaks not found. Download from https://github.com/gitleaks/gitleaks/releases "
        "and place gitleaks.exe in the backend_new folder."
    )


def run_gitleaks(repo_path: str) -> list:
    """
    Run Gitleaks on the cloned repo to detect hardcoded secrets.
    Returns list of findings.
    """
    try:
        gitleaks_cmd = _find_gitleaks()
        report_path  = os.path.join(repo_path, "gitleaks_report.json")

        result = subprocess.run(
            [
                gitleaks_cmd,
                "detect",
                "--source", repo_path,
                "--report-format", "json",
                "--report-path", report_path,
                "--no-git",
                "--exit-code", "0"  # don't fail on findings
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120
        )

        if not os.path.exists(report_path):
            print("[Gitleaks] No report file generated.")
            return []

        with open(report_path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)

        if not data:
            print("[Gitleaks] No secrets found.")
            return []

        issues = []
        for finding in data:
            # Redact the actual secret value for safety
            secret_val = finding.get("Secret", "")
            redacted   = secret_val[:4] + "****" + secret_val[-2:] if len(secret_val) > 6 else "****"

            issues.append({
                "tool":        "gitleaks",
                "severity":    "critical",  # hardcoded secrets are always critical
                "message":     f"{finding.get('Description', 'Secret detected')} — Rule: {finding.get('RuleID', '')}",
                "file":        finding.get("File", "").replace(repo_path, "").replace(repo_path.replace("\\", "/"), "").lstrip("/\\").replace("\\", "/"),
                "line":        finding.get("StartLine", 0),
                "rule_id":     finding.get("RuleID", ""),
                "secret_type": finding.get("Description", ""),
                "redacted":    redacted,
                "commit":      finding.get("Commit", ""),
            })

        print(f"[Gitleaks] Found {len(issues)} secret(s).")
        return issues

    except FileNotFoundError as e:
        print(f"[Gitleaks] {e}")
        return []
    except subprocess.TimeoutExpired:
        print("[Gitleaks] Timed out.")
        return []
    except Exception as e:
        print(f"[Gitleaks] Error: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# CHECKOV
# ══════════════════════════════════════════════════════════════════════════════
def run_checkov(repo_path: str) -> list:
    """
    Run Checkov on the cloned repo to detect IaC misconfigurations.
    Scans Dockerfiles, GitHub Actions, Terraform, K8s, etc.
    """
    try:
        # Delete gitleaks report so Checkov doesn't scan it
        gitleaks_report = os.path.join(repo_path, "gitleaks_report.json")
        if os.path.exists(gitleaks_report):
            os.remove(gitleaks_report)

        python_exe = _sys.executable  # use same venv Python

        result = subprocess.run(
            [
                python_exe, "-m", "checkov.main",
                "--directory", repo_path,
                "--output", "json",
                "--quiet",
                "--compact",
                "--soft-fail",        # don't exit with error code on findings
                "--skip-check",       # skip checks that are too noisy
                "CKV_DOCKER_2,"       # skip HEALTHCHECK (too noisy)
                "CKV_DOCKER_7,"       # skip non-root user in every image
                "CKV2_GHA_1"          # skip pinned actions (too noisy for students)
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300
        )

        stdout = result.stdout.decode("utf-8", errors="ignore").strip()
        if not stdout:
            print("[Checkov] No output received.")
            return []

        # Checkov sometimes outputs multiple JSON objects — take the last valid one
        data = None
        for chunk in stdout.split("\n"):
            chunk = chunk.strip()
            if chunk.startswith("{") or chunk.startswith("["):
                try:
                    data = json.loads(chunk)
                    break
                except json.JSONDecodeError:
                    continue

        if not data:
            try:
                data = json.loads(stdout)
            except json.JSONDecodeError:
                print("[Checkov] Could not parse JSON output.")
                return []

        severity_map = {
            "HIGH":   "high",
            "MEDIUM": "medium",
            "LOW":    "low",
            "CRITICAL": "critical"
        }

        issues = []

        # Handle both single result object and list of results
        results_list = data if isinstance(data, list) else [data]

        for result_block in results_list:
            if not isinstance(result_block, dict):
                continue

            results = result_block.get("results", {})
            failed  = results.get("failed_checks", [])

            for check in failed:
                sev_raw  = check.get("severity") or "MEDIUM"
                file_abs  = check.get("repo_file_path", check.get("file_path", ""))
                # Normalize all path separators then make relative
                file_norm = file_abs.replace("\\", "/")
                repo_norm = repo_path.replace("\\", "/")
                # Try various combinations to strip the temp path
                for prefix in [repo_norm, repo_norm.rstrip("/"), repo_path, repo_path.rstrip("\\")]:
                    prefix_norm = prefix.replace("\\", "/")
                    if file_norm.startswith(prefix_norm):
                        file_norm = file_norm[len(prefix_norm):]
                        break
                    # Handle Windows short path vs long path differences
                    import re as _re2
                    # Strip anything that looks like a temp path prefix
                    file_norm = _re2.sub(r'^.*?/Temp/tmp[^/]+/', '', file_norm)
                    file_norm = _re2.sub(r'^.*?\\Temp\\tmp[^\\]+\\', '', file_norm)
                    break
                file_rel = file_norm.lstrip("/\\")

                # Clean resource path
                resource_raw  = check.get("resource", "")
                resource_clean = resource_raw.replace("\\", "/").replace("//", "/").strip("/").strip(".")

                issues.append({
                    "tool":        "checkov",
                    "severity":    severity_map.get(str(sev_raw).upper(), "medium"),
                    "message":     check.get("check_name", check.get("check_id", "Unknown check")),
                    "file":        file_rel,
                    "line":        check.get("file_line_range", [0])[0] if check.get("file_line_range") else 0,
                    "rule_id":     check.get("check_id", ""),
                    "check_name":  check.get("check_name", ""),
                    "resource":    resource_clean,
                })

        print(f"[Checkov] Found {len(issues)} misconfiguration(s).")
        return issues

    except subprocess.TimeoutExpired:
        print("[Checkov] Timed out.")
        return []
    except Exception as e:
        print(f"[Checkov] Error: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# GROQ ENRICHMENT for Gitleaks + Checkov
# ══════════════════════════════════════════════════════════════════════════════
def _extract_retry_delay(error_str: str) -> float:
    match = re.search(r'try again in (\d+(?:\.\d+)?)s', str(error_str), re.IGNORECASE)
    if match:
        return float(match.group(1)) + 2.0
    return 10.0


def _enrich_extra_issue(issue: dict, retries: int = 5) -> dict:
    """Enrich a Gitleaks or Checkov finding with Groq explanation and fix."""
    for attempt in range(retries):
        try:
            tool       = issue.get("tool", "")
            message    = issue.get("message", "")
            file       = issue.get("file", "")
            line       = issue.get("line", 0)

            if tool == "gitleaks":
                secret_type = issue.get("secret_type", "")
                redacted    = issue.get("redacted", "****")
                file_display = file.split("/")[-1] if "/" in file else file.split("\\")[-1] if "\\" in file else file
                prompt = f"""You are a senior developer helping a junior developer fix a critical security issue.
A hardcoded secret was found directly in the source code. Explain this like the developer has never seen this issue before.

Secret Type: {secret_type}
File: {file_display} (full path: {file})
Line: {line}
Redacted Value: {redacted}

Respond in this exact JSON format only, no markdown, no preamble:
{{
  "explanation": "3-4 sentences in plain English: (1) What exactly was found and where — name the file and line. (2) Explain what this secret is used for in simple terms (e.g. 'This is an API key that gives access to your GitHub account'). (3) What happens if someone finds this — be specific and scary but true (e.g. 'Anyone who reads your code on GitHub can copy this key and use your account to delete repos, steal private code, or rack up charges'). (4) Why putting secrets in code is always wrong.",
  "fix": "Step by step instructions written like you are pair programming with them: Step 1 — RIGHT NOW go to <the service website> and revoke/regenerate this key immediately before doing anything else. Step 2 — Open the file {file}, find line {line}, and delete that line completely. Step 3 — Create a .env file in your project root if you don\'t have one, and add this line: SECRET_NAME=your_new_key_here. Step 4 — In your code, replace the hardcoded value with: import os; secret = os.environ.get(\'SECRET_NAME\'). Step 5 — Add .env to your .gitignore file so it never gets committed. Step 6 — Run git log to check if this secret was committed before — if yes, you need to rewrite git history or the secret is still exposed."
}}"""

            else:  # checkov
                check_name = issue.get("check_name", "")
                resource   = issue.get("resource", "")
                prompt = f"""You are a senior developer helping a junior developer fix a security misconfiguration in their infrastructure code.
Explain this like the developer is new to Docker/GitHub Actions/Terraform and has never heard of this issue before.

Issue: {check_name}
Rule: {issue.get('rule_id', '')}
File: {file}
Line: {line}
Resource: {resource}

Respond in this exact JSON format only, no markdown, no preamble:
{{
  "explanation": "3-4 sentences in plain English: (1) What exactly is wrong in the file at that line — describe what the code currently does. (2) Explain WHY this is a problem in simple terms a beginner understands (e.g. \'Right now your Docker container runs as the root user, which is like running everything as an admin — if someone hacks your app, they get full control of the server\'). (3) What could go wrong if this is exploited — give a real world example. (4) How common this mistake is and why developers miss it.",
  "fix": "Step by step instructions written like you are sitting next to them: Step 1 — Open {file} and go to line {line}. Step 2 — Here is exactly what to add/change: show the specific lines to add or modify with actual code. Step 3 — Explain what each added line does in plain English. Step 4 — How to verify the fix worked."
}}"""

            response = GROQ_CLIENT.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )

            text = response.choices[0].message.content.strip()
            text = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()

            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                exp_match = re.search(r'"explanation"\s*:\s*"(.*?)"(?:\s*,|\s*})', text, re.DOTALL)
                fix_match = re.search(r'"fix"\s*:\s*"(.*?)"(?:\s*,|\s*})', text, re.DOTALL)
                parsed = {
                    "explanation": exp_match.group(1).strip() if exp_match else "",
                    "fix":         fix_match.group(1).strip() if fix_match else ""
                }

            issue["explanation"] = parsed.get("explanation", "")
            issue["fix"]         = parsed.get("fix", "")
            return issue

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate_limit" in error_str.lower():
                wait = _extract_retry_delay(error_str)
                print(f"[Enrichment-Extra] Rate limited. Waiting {wait:.0f}s (attempt {attempt+1}/{retries})...")
                time.sleep(wait)
            elif "503" in error_str or "unavailable" in error_str.lower():
                wait = (2 ** attempt) * 5
                print(f"[Enrichment-Extra] Server overloaded. Waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"[Enrichment-Extra] Failed: {e}")
                issue["explanation"] = ""
                issue["fix"]         = ""
                return issue

    issue["explanation"] = ""
    issue["fix"]         = ""
    return issue


def enrich_extra_issues(issues: list) -> list:
    """Deduplicate and enrich Gitleaks + Checkov findings."""
    # Deduplicate — for gitleaks use file+line as key (each occurrence is unique)
    # for checkov use rule_id+file (same rule in same file = duplicate)
    seen   = set()
    unique = []
    for issue in issues:
        tool = issue.get("tool", "")
        if tool == "gitleaks":
            key = f"gitleaks|{issue.get('file')}|{issue.get('line')}|{issue.get('rule_id')}"
        else:
            key = f"{tool}|{issue.get('rule_id')}|{issue.get('file')}|{issue.get('line')}"
        if key not in seen:
            seen.add(key)
            unique.append(issue)

    removed = len(issues) - len(unique)
    if removed:
        print(f"[Enrichment-Extra] Deduplicated {len(issues)} → {len(unique)} ({removed} removed).")

    enriched = []
    calls    = 0
    seen_enrich = {}

    for issue in unique:
        tool = issue.get("tool", "")
        if tool == "gitleaks":
            # Each file gets its own enrichment so the explanation references the correct file
            enrich_key = f"gitleaks|{issue.get('rule_id')}|{issue.get('file')}"
        else:
            enrich_key = f"{tool}|{issue.get('rule_id', issue.get('message', '')[:80])}"

        if enrich_key in seen_enrich:
            issue["explanation"] = seen_enrich[enrich_key]["explanation"]
            issue["fix"]         = seen_enrich[enrich_key]["fix"]
        else:
            print(f"[Enrichment-Extra] Enriching {calls+1}: {enrich_key[:70]}")
            issue = _enrich_extra_issue(issue)
            seen_enrich[enrich_key] = {"explanation": issue["explanation"], "fix": issue["fix"]}
            calls += 1
            time.sleep(2)

        enriched.append(issue)

    print(f"[Enrichment-Extra] {calls} Groq calls for {len(unique)} unique issues.")
    return enriched


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
def run_extras(repo_path: str) -> dict:
    """
    Run Gitleaks and Checkov on the cloned repo.
    Returns enriched findings for both tools.
    """
    gitleaks_issues = run_gitleaks(repo_path)
    checkov_issues  = run_checkov(repo_path)

    all_issues = gitleaks_issues + checkov_issues

    if all_issues:
        print(f"[Extras] Enriching {len(all_issues)} Gitleaks + Checkov findings...")
        all_issues = enrich_extra_issues(all_issues)

    return {
        "gitleaks": [i for i in all_issues if i.get("tool") == "gitleaks"],
        "checkov":  [i for i in all_issues if i.get("tool") == "checkov"],
    }