# run_live.py

import asyncio

from engine.live.multi_chain_orchestrator import MultiChainOrchestrator
from engine.utils.logger import setup_logger

# -------------------------------------------------
# CONFIG
# -------------------------------------------------

INITIAL_EQUITY = 1000.0

# MULTI-SYMBOL LIST (engine currently uses first symbol)
BINANCE_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
]

BINANCE_INTERVAL = "5m"

LOOP_INTERVAL = 10
MAX_DRAWDOWN = 0.20


async def main():

    # -------------------------------------------------
    # LOGGER
    # -------------------------------------------------

    logger = setup_logger()

    logger.info("Starting Crypto Trader V2")

    # -------------------------------------------------
    # SOLANA SETUP (SAFE PAPER MODE)
    # -------------------------------------------------

    from engine.execution.solana.solana_executor import SolanaExecutor

    solana_executor = SolanaExecutor(
        wallet=None,
        jupiter=None,
        mode="paper",
    )

    # -------------------------------------------------
    # BASE SETUP (SAFE PAPER MODE)
    # -------------------------------------------------

    from engine.execution.base.base_executor import BaseExecutor
    from engine.execution.base.base_web3_provider import BaseWeb3Provider
    from engine.execution.base.base_v3_pool import BaseV3Pool
    from engine.execution.base.base_v3_math_quoter import BaseV3MathQuoter
    from engine.execution.base.base_live_executor import BaseLiveExecutor

    provider = BaseWeb3Provider(logger)
    pool = BaseV3Pool(provider, logger)
    quoter = BaseV3MathQuoter(pool, logger)

    base_live = BaseLiveExecutor(
        provider=provider,
        quoter=quoter,
        logger=logger,
        dry_run=True,  # prevents real swaps
    )

    base_executor = BaseExecutor(
        live_executor=base_live,
        mode="paper",
    )

    # -------------------------------------------------
    # EXECUTOR MAP
    # -------------------------------------------------

    executors = {
        "solana": solana_executor,
        "base": base_executor,
    }

    # -------------------------------------------------
    # SELECT SYMBOL (TEMPORARY UNTIL MULTI-SYMBOL ENGINE)
    # -------------------------------------------------

    symbol = BINANCE_SYMBOLS[0]

    logger.info(f"Trading symbol: {symbol}")

    # -------------------------------------------------
    # ORCHESTRATOR
    # -------------------------------------------------

    orchestrator = MultiChainOrchestrator(
        executors=executors,
        symbol=symbol,
        interval=BINANCE_INTERVAL,
        loop_interval=LOOP_INTERVAL,
        initial_equity=INITIAL_EQUITY,
        max_drawdown=MAX_DRAWDOWN,
    )

    logger.info("Engine initialized. Entering run loop.")

    await orchestrator.run()


if __name__ == "__main__":
    asyncio.run(main())