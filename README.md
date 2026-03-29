# PR Security Scanner

A multi-tool security audit system for GitHub Pull Requests. Combines static analysis, dependency scanning, secret detection, IaC misconfiguration detection, and AI-powered deep audit into a single JSON output.

## Tools Used

| Tool | What it detects | How it's installed |
|---|---|---|
| **Semgrep** | Code vulnerabilities (SQL injection, XSS, eval, etc.) | `pip install semgrep` |
| **OSV Scanner** | Known CVEs in dependencies | Binary download (see setup) |
| **Gitleaks** | Hardcoded secrets, API keys, tokens | Binary download (see setup) |
| **Checkov** | Dockerfile, GitHub Actions, IaC misconfigurations | `pip install checkov` |
| **AI Agent (Groq LLaMA)** | Deep reasoning on PR diff — logic flaws, auth bypass, novel vulns | Groq API key (free) |

## Prerequisites

- Python 3.11+
- Git

## Setup

### 0. Tool-specific setup notes

#### Semgrep
- Installed via pip: `pip install semgrep`
- Auto-detected by the scanner — no extra config needed
- Uses `p/security-audit` ruleset — downloads automatically on first run

#### OSV Scanner
- Single binary, no install needed
- Download the correct binary for your OS from https://github.com/google/osv-scanner/releases/latest
- Place it in `backend_new/` folder
- Windows: `osv-scanner_windows_amd64.exe`
- Mac: `osv-scanner_darwin_amd64` → rename to `osv-scanner` and run `chmod +x osv-scanner`
- Linux: `osv-scanner_linux_amd64` → rename to `osv-scanner` and run `chmod +x osv-scanner`

#### Gitleaks
- Single binary, no install needed
- Download from https://github.com/gitleaks/gitleaks/releases/latest
- Windows: extract `gitleaks.exe` from zip, place in `backend_new/`
- Mac/Linux: extract `gitleaks` binary, place in `backend_new/`, run `chmod +x gitleaks`

#### Checkov
- Installed via pip: `pip install checkov`
- Auto-detected by the scanner — no extra config needed
- Scans Dockerfiles, GitHub Actions YAML, Terraform, K8s manifests automatically

#### AI Agent (Groq + LLaMA 3.3 70B)
- Uses Groq's free API — no local GPU needed
- Sign up at https://console.groq.com (free, no credit card)
- Create an API key and add it to `.env` as both `GROQ_API_KEY` and `AI_API_TOKEN`
- The agent patches `seclab-taskflow-agent` to work with Groq's OpenAI-compatible endpoint
- After installing requirements, run these patches:
```bash
# patch the seclab agent to support Groq endpoint
python -c "
import os, sys
path = os.path.join(sys.prefix, 'Lib', 'site-packages', 'seclab_taskflow_agent', 'agent.py')
with open(path) as f: c = f.read()
old = '''    case _:
        raise ValueError(
            f\"Unsupported Model Endpoint: {api_endpoint}\\n\"
            f\"Supported endpoints: {[e.to_url() for e in AI_API_ENDPOINT_ENUM]}\"
        )'''
new = '    case _:\n        default_model = \"llama-3.3-70b-versatile\"  # Groq patch'
if old in c:
    open(path, 'w').write(c.replace(old, new))
    print('agent.py patched!')
else:
    print('already patched or pattern changed')
"
```

### 1. Clone the repo

```bash
git clone https://github.com/Arjun7A/Code_Editor-Arjun-.git
cd Code_Editor-Arjun-/backend_new
```

### 2. Create virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Download required binaries

Place these in the `backend_new/` folder:

**OSV Scanner** (dependency vulnerability scanner):
- Download from: https://github.com/google/osv-scanner/releases/latest
- Windows: `osv-scanner_windows_amd64.exe`
- Mac: `osv-scanner_darwin_amd64`
- Linux: `osv-scanner_linux_amd64`

**Gitleaks** (secret scanner):
- Download from: https://github.com/gitleaks/gitleaks/releases/latest
- Windows: extract `gitleaks.exe` from the zip
- Mac/Linux: extract `gitleaks` binary

### 5. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in your keys:

```env
GROQ_API_KEY=your_groq_api_key        # from https://console.groq.com
GITHUB_USER_TOKEN=your_github_pat     # from GitHub Settings > Developer Settings > PAT
AI_API_TOKEN=your_groq_api_key        # same as GROQ_API_KEY
AI_API_ENDPOINT=https://api.groq.com/openai/v1
GROQ_MODEL=llama-3.3-70b-versatile
```

**Getting a Groq API key:**
1. Go to https://console.groq.com
2. Sign up (free)
3. Create an API key

**Getting a GitHub PAT:**
1. Go to GitHub → Settings → Developer Settings → Personal Access Tokens → Tokens (classic)
2. Generate new token with `repo` scope

### 6. Install Semgrep and Checkov

```bash
pip install semgrep checkov
```

> **Note:** Semgrep and Checkov are installed via pip. Gitleaks is a binary downloaded in Step 4.

### 7. Run the server

```bash
python main.py
```

Server runs at: `http://127.0.0.1:8001`

## Optional: Blockchain Anchoring

The backend now supports recording each scan hash on an EVM-compatible chain.

Add these environment variables in `backend_new/.env`:

```env
BLOCKCHAIN_ENABLED=true
BLOCKCHAIN_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com
BLOCKCHAIN_PRIVATE_KEY=0x...
BLOCKCHAIN_CHAIN_ID=11155111
BLOCKCHAIN_NETWORK_NAME=Ethereum Sepolia
BLOCKCHAIN_EXPLORER_TX_BASE=https://sepolia.etherscan.io/tx

# Optional
BLOCKCHAIN_TO_ADDRESS=0x...            # defaults to sender wallet
BLOCKCHAIN_GAS_LIMIT=100000
BLOCKCHAIN_TX_TIMEOUT=180
```

If blockchain is not configured (or a transaction fails), the API still works and returns a local integrity hash record with `verified: false`.

### Supabase migration for blockchain field

If your `scan_history` table already exists, run:

```sql
alter table public.scan_history
  add column if not exists blockchain_verification jsonb;
```

## API Usage

### Analyze a PR

```
POST http://127.0.0.1:8001/analyze-pr
Content-Type: application/json

{
  "repo_url": "https://github.com/owner/repo",
  "pr_url": "https://github.com/owner/repo/pull/123"
}
```

### Response Structure

```json
{
  "repo_url": "...",
  "pr_url": "...",
  "scan_summary": {
    "total_issues": 38,
    "semgrep": 1,
    "osv": 35,
    "ai_agent": 0,
    "gitleaks": 0,
    "checkov": 2,
    "pr_files_scanned": 13
  },
  "issues": [...],      
  "ai_audit": {...},    
  "gitleaks": [...],    
  "checkov": [...],
  "blockchain_verification": {
    "auditHash": "0x...",
    "transactionHash": "0x...",
    "blockNumber": 123456,
    "timestamp": "2026-03-29T08:42:10+00:00",
    "network": "Ethereum Sepolia",
    "explorerUrl": "https://sepolia.etherscan.io/tx/0x...",
    "verified": true
  }
}
```

## Notes for Mac/Linux users

- Replace `osv-scanner_windows_amd64.exe` with the appropriate binary for your OS
- Make the binary executable: `chmod +x osv-scanner_linux_amd64`
- Set `SEMGREP_PATH` in `.env` if semgrep is not auto-detected
- Gitleaks binary should also be made executable: `chmod +x gitleaks`
