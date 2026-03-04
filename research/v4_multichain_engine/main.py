import asyncio
import time

from research.v4_multichain_engine.data_loader import DataLoader
from research.v4_multichain_engine.multi_chain_orchestrator import MultiChainOrchestrator


async def main():

    print("DATA LOADER INITIALIZED")

    data_loader = DataLoader()

    print(f"Base path: {data_loader.base_path}")

    orchestrator = MultiChainOrchestrator(data_loader)

    start_time = time.perf_counter()

    await orchestrator.run_portfolio()

    end_time = time.perf_counter()

    print("\n=======================================")
    print(f"Total runtime: {end_time - start_time:.2f} seconds")
    print("=======================================\n")


# ==========================================================
# Windows multiprocessing safety guard
# REQUIRED when using ProcessPoolExecutor
# ==========================================================

if __name__ == "__main__":
    asyncio.run(main())