from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
from typing import Any

try:
    from web3 import Web3
except ImportError:  # pragma: no cover - runtime optional dependency
    Web3 = None

LOGGER = logging.getLogger("secureaudit.blockchain")
AMOY_CHAIN_ID = 80002
AMOY_NETWORK_NAME = "Polygon Amoy"
AMOY_EXPLORER_TX_BASE = "https://amoy.polygonscan.com/tx"
SEPOLIA_CHAIN_ID = 11155111
SEPOLIA_NETWORK_NAME = "Ethereum Sepolia"
SEPOLIA_EXPLORER_TX_BASE = "https://sepolia.etherscan.io/tx"


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _truthy(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _safe_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _canonical_scan_payload(scan: dict[str, Any]) -> dict[str, Any]:
    """
    Keep only deterministic scan content for hashing.
    Excluding metadata avoids circular hash updates and keeps payload stable.
    """
    return {
        "repo_url": scan.get("repo_url", ""),
        "pr_url": scan.get("pr_url", ""),
        "scanned_at": scan.get("scanned_at", ""),
        "scan_summary": scan.get("scan_summary", {}) or {},
        "issues": scan.get("issues", []) or [],
        "ai_audit": scan.get("ai_audit", {}) or {},
        "gitleaks": scan.get("gitleaks", []) or [],
        "checkov": scan.get("checkov", []) or [],
    }


def compute_audit_hash(scan: dict[str, Any]) -> str:
    payload = _safe_json(_canonical_scan_payload(scan))
    return f"0x{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _build_explorer_url(tx_hash: str, chain_id: int) -> str:
    base = (os.getenv("BLOCKCHAIN_EXPLORER_TX_BASE") or "").strip()
    if not base:
        if chain_id == AMOY_CHAIN_ID:
            base = AMOY_EXPLORER_TX_BASE
        elif chain_id == SEPOLIA_CHAIN_ID:
            base = SEPOLIA_EXPLORER_TX_BASE
    if not base:
        return ""
    return f"{base.rstrip('/')}/{tx_hash}"


def _fallback_verification(scan: dict[str, Any], *, network: str | None = None) -> dict[str, Any]:
    audit_hash = compute_audit_hash(scan)
    return {
        "auditHash": audit_hash,
        "transactionHash": audit_hash,
        "blockNumber": 0,
        "timestamp": _utc_now_iso(),
        "network": network or os.getenv("BLOCKCHAIN_NETWORK_NAME", "Local Integrity Ledger"),
        "explorerUrl": "",
        "verified": False,
    }


def record_scan_verification(scan: dict[str, Any]) -> dict[str, Any]:
    """
    Attempts to anchor the scan hash on-chain.
    If chain config is missing or tx fails, returns a local integrity record.
    """
    if not _truthy(os.getenv("BLOCKCHAIN_ENABLED")):
        return _fallback_verification(scan)

    if Web3 is None:
        LOGGER.warning("web3 is unavailable; blockchain verification disabled.")
        return _fallback_verification(scan)

    rpc_url = (os.getenv("BLOCKCHAIN_RPC_URL") or "").strip()
    private_key = (os.getenv("BLOCKCHAIN_PRIVATE_KEY") or "").strip()

    if not rpc_url or not private_key:
        LOGGER.warning("Missing BLOCKCHAIN_RPC_URL or BLOCKCHAIN_PRIVATE_KEY.")
        return _fallback_verification(scan)

    audit_hash = compute_audit_hash(scan)

    try:
        web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
        if not web3.is_connected():
            LOGGER.warning("Unable to connect to blockchain RPC provider.")
            return _fallback_verification(scan)

        account = web3.eth.account.from_key(private_key)
        chain_id_value = os.getenv("BLOCKCHAIN_CHAIN_ID")
        chain_id = int(chain_id_value) if chain_id_value else int(web3.eth.chain_id)

        destination = (os.getenv("BLOCKCHAIN_TO_ADDRESS") or account.address).strip()
        to_address = Web3.to_checksum_address(destination)

        tx: dict[str, Any] = {
            "chainId": chain_id,
            "from": account.address,
            "to": to_address,
            "value": 0,
            "nonce": web3.eth.get_transaction_count(account.address),
            "data": audit_hash,
            "gasPrice": web3.eth.gas_price,
        }

        try:
            tx["gas"] = web3.eth.estimate_gas(tx)
        except Exception:
            tx["gas"] = int(os.getenv("BLOCKCHAIN_GAS_LIMIT", "100000"))

        signed_tx = web3.eth.account.sign_transaction(tx, private_key=private_key)
        tx_hash_bytes = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        tx_hash = Web3.to_hex(tx_hash_bytes)

        receipt_timeout = int(os.getenv("BLOCKCHAIN_TX_TIMEOUT", "180"))
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=receipt_timeout)

        block = web3.eth.get_block(receipt.blockNumber)
        block_time = datetime.datetime.fromtimestamp(
            block.timestamp, tz=datetime.timezone.utc
        ).isoformat()

        network_name = os.getenv(
            "BLOCKCHAIN_NETWORK_NAME",
            (
                AMOY_NETWORK_NAME
                if chain_id == AMOY_CHAIN_ID
                else SEPOLIA_NETWORK_NAME
                if chain_id == SEPOLIA_CHAIN_ID
                else f"chain-id {chain_id}"
            ),
        )

        return {
            "auditHash": audit_hash,
            "transactionHash": tx_hash,
            "blockNumber": int(receipt.blockNumber),
            "timestamp": block_time,
            "network": network_name,
            "explorerUrl": _build_explorer_url(tx_hash, chain_id),
            "verified": bool(receipt.status == 1),
        }
    except Exception as exc:  # pragma: no cover - depends on runtime chain env
        LOGGER.exception("Blockchain anchoring failed: %s", exc)
        return _fallback_verification(scan)
