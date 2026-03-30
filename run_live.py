# run_live.py

import asyncio

from engine.live.multi_chain_orchestrator import MultiChainOrchestrator
from engine.utils.logger import setup_logger

from engine.config.config import ENGINE_CONFIG
from engine.config.symbols import SYMBOLS


INITIAL_EQUITY = ENGINE_CONFIG.get("starting_equity", 1000.0)
BINANCE_SYMBOLS = SYMBOLS
BINANCE_INTERVAL = "1h"
LOOP_INTERVAL = ENGINE_CONFIG.get("loop_interval", 10)
MAX_DRAWDOWN = ENGINE_CONFIG.get("portfolio_circuit_breaker_dd", 0.20)


async def main():
    logger = setup_logger()
    logger.info("Starting Crypto Trader V2")

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
        dry_run=False,
    )

    base_executor = BaseExecutor(
        live_executor=base_live,
        mode="live",
    )

    executors = {
        "base": base_executor,
    }

    logger.info(f"Trading symbols: {BINANCE_SYMBOLS}")

    orchestrator = MultiChainOrchestrator(
        executors=executors,
        symbol=BINANCE_SYMBOLS[0],
        interval=BINANCE_INTERVAL,
        loop_interval=LOOP_INTERVAL,
        initial_equity=INITIAL_EQUITY,
        max_drawdown=MAX_DRAWDOWN,
    )

    logger.info("Engine initialized. Entering run loop.")
    await orchestrator.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutdown requested by user.")