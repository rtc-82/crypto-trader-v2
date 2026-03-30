from __future__ import annotations

from typing import Dict, Any
from web3 import Web3


ZERO_ADDRESS = Web3.to_checksum_address("0x0000000000000000000000000000000000000000")

USDC_ADDRESS = Web3.to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
WETH_ADDRESS = Web3.to_checksum_address("0x4200000000000000000000000000000000000006")

AAVE_BASE_ADDRESS = Web3.to_checksum_address("0x63706e401c06ac8513145b7687a14804d17f814b")


BASE_TOKEN_REGISTRY: Dict[str, Dict[str, Any]] = {
    "USDC": {
        "symbol": "USDC",
        "address": USDC_ADDRESS,
        "decimals": 6,
        "live_ready": True,
        "trade": {},
    },
    "WETH": {
        "symbol": "WETH",
        "address": WETH_ADDRESS,
        "decimals": 18,
        "live_ready": True,
        "trade": {
            "quote_symbol": "USDC",
            "fee": 3000,
        },
    },

    "AAVE": {
        "symbol": "AAVE",
        "address": AAVE_BASE_ADDRESS,
        "decimals": 18,
        "live_ready": True,
        "trade": {
            "quote_symbol": "USDC",
            "fee": 3000,
        },
    },

    # No official verified RENDER token on Base in your current plan.
    # Keep blocked until you add a verified non-Base route instead.
    "RENDER": {
        "symbol": "RENDER",
        "address": ZERO_ADDRESS,
        "decimals": 18,
        "live_ready": False,
        "trade": {
            "quote_symbol": "USDC",
            "fee": 3000,
        },
    },
}


def get_token_config(symbol: str) -> Dict[str, Any]:
    key = str(symbol).strip().upper()

    if key not in BASE_TOKEN_REGISTRY:
        raise KeyError(f"Unknown Base token symbol: {symbol}")

    return BASE_TOKEN_REGISTRY[key]


def get_token_address(symbol: str) -> str:
    return str(get_token_config(symbol)["address"])


def get_token_decimals(symbol: str) -> int:
    return int(get_token_config(symbol)["decimals"])


def get_trade_config(symbol: str) -> Dict[str, Any]:
    cfg = get_token_config(symbol)
    return dict(cfg.get("trade", {}) or {})


def ensure_live_ready(symbol: str) -> Dict[str, Any]:
    cfg = get_token_config(symbol)
    address = Web3.to_checksum_address(cfg["address"])

    if address == ZERO_ADDRESS:
        raise RuntimeError(
            f"{symbol} is not live-ready: token address is still ZERO_ADDRESS in base_tokens.py"
        )

    if not bool(cfg.get("live_ready", False)):
        raise RuntimeError(
            f"{symbol} is not live-ready: set live_ready=True only after verifying address/decimals"
        )

    return cfg