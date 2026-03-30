from __future__ import annotations

from typing import Dict, Tuple, Any
from web3 import Web3
import logging


UNISWAP_V3_FACTORY = Web3.to_checksum_address(
    "0x33128a8fC17869897dcE68Ed026d694621f6FDfD"
)

ZERO_ADDRESS = Web3.to_checksum_address("0x0000000000000000000000000000000000000000")


FACTORY_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
        ],
        "name": "getPool",
        "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    }
]


POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "token1",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class BaseV3Pool:
    """
    Generic Uniswap V3 pool accessor.

    This version no longer assumes only WETH/USDC.
    """

    def __init__(self, provider, logger: logging.Logger, fee: int = 3000):
        self.provider = provider
        self.logger = logger
        self.w3 = provider.w3
        self.default_fee = int(fee)

        self.factory = self.w3.eth.contract(
            address=UNISWAP_V3_FACTORY,
            abi=FACTORY_ABI,
        )

        self._pool_cache: Dict[Tuple[str, str, int], Dict[str, Any]] = {}

    def _pair_key(self, token_a: str, token_b: str, fee: int) -> Tuple[str, str, int]:
        a = Web3.to_checksum_address(token_a)
        b = Web3.to_checksum_address(token_b)
        ordered = tuple(sorted([a, b]))
        return ordered[0], ordered[1], int(fee)

    def get_pool(self, token_a: str, token_b: str, fee: int | None = None) -> Dict[str, Any]:
        fee = int(self.default_fee if fee is None else fee)
        key = self._pair_key(token_a, token_b, fee)

        if key in self._pool_cache:
            return self._pool_cache[key]

        token_a = Web3.to_checksum_address(token_a)
        token_b = Web3.to_checksum_address(token_b)

        pool_address = self.factory.functions.getPool(
            token_a,
            token_b,
            fee,
        ).call()

        if Web3.to_checksum_address(pool_address) == ZERO_ADDRESS:
            raise RuntimeError(f"Pool not found for pair {token_a}/{token_b} fee={fee}")

        pool_contract = self.w3.eth.contract(
            address=pool_address,
            abi=POOL_ABI,
        )

        token0 = Web3.to_checksum_address(pool_contract.functions.token0().call())
        token1 = Web3.to_checksum_address(pool_contract.functions.token1().call())

        payload = {
            "address": Web3.to_checksum_address(pool_address),
            "contract": pool_contract,
            "token0": token0,
            "token1": token1,
            "fee": fee,
        }

        self._pool_cache[key] = payload

        self.logger.info(
            "V3 Pool loaded: %s token0=%s token1=%s fee=%s",
            payload["address"],
            token0,
            token1,
            fee,
        )

        return payload

    def get_price(
        self,
        token_base: str,
        token_quote: str,
        base_decimals: int,
        quote_decimals: int,
        fee: int | None = None,
    ) -> float:
        """
        Returns quote-token per base-token spot price.
        Example:
            base=AAVE, quote=USDC -> USDC per AAVE
        """
        token_base = Web3.to_checksum_address(token_base)
        token_quote = Web3.to_checksum_address(token_quote)

        pool_info = self.get_pool(token_base, token_quote, fee)
        pool = pool_info["contract"]

        slot0 = pool.functions.slot0().call()
        sqrt_price_x96 = slot0[0]

        raw_price = (sqrt_price_x96 / (2 ** 96)) ** 2

        token0 = pool_info["token0"]
        token1 = pool_info["token1"]

        decimal_adjustment = 10 ** (int(base_decimals) - int(quote_decimals))

        if token0 == token_base and token1 == token_quote:
            return raw_price * decimal_adjustment

        if token0 == token_quote and token1 == token_base:
            if raw_price <= 0:
                raise RuntimeError("Invalid pool raw price (<= 0).")
            return (1.0 / raw_price) * decimal_adjustment

        raise RuntimeError(
            f"Pool token mismatch for requested pair base={token_base} quote={token_quote}"
        )

    def get_liquidity(self, token_a: str, token_b: str, fee: int | None = None) -> int:
        pool_info = self.get_pool(token_a, token_b, fee)
        return int(pool_info["contract"].functions.liquidity().call())