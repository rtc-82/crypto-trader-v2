from __future__ import annotations

from web3 import Web3
import logging


UNISWAP_V3_FACTORY = Web3.to_checksum_address(
    "0x33128a8fC17869897dcE68Ed026d694621f6FDfD"
)

WETH = Web3.to_checksum_address(
    "0x4200000000000000000000000000000000000006"
)

USDC = Web3.to_checksum_address(
    "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
)


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
    def __init__(self, provider, logger: logging.Logger, fee: int = 3000):
        self.provider = provider
        self.logger = logger
        self.w3 = provider.w3
        self.fee = fee

        factory = self.w3.eth.contract(
            address=UNISWAP_V3_FACTORY,
            abi=FACTORY_ABI,
        )

        pool_address = factory.functions.getPool(
            WETH,
            USDC,
            self.fee,
        ).call()

        if pool_address == "0x0000000000000000000000000000000000000000":
            raise RuntimeError("Pool not found.")

        self.pool_address = pool_address
        self.pool = self.w3.eth.contract(
            address=pool_address,
            abi=POOL_ABI,
        )

        self.logger.info(f"V3 Pool loaded: {self.pool_address}")

    def get_price(self) -> float:
        slot0 = self.pool.functions.slot0().call()
        sqrt_price_x96 = slot0[0]

        price = (sqrt_price_x96 / (2 ** 96)) ** 2

        # Adjust for decimals (WETH 18, USDC 6)
        adjusted_price = price * (10 ** 12)

        return adjusted_price

    def get_liquidity(self) -> int:
        return self.pool.functions.liquidity().call()