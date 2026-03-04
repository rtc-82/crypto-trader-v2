# engine/execution/solana/jupiter_execution_engine.py

class JupiterExecutionEngine:
    def __init__(self, wallet=None, config=None, mode="paper"):
        self.wallet = wallet
        self.config = config
        self.mode = mode

    async def swap_sol_to_usdc(self, sol_amount: float):
        if self.mode == "paper":
            return {"tx_id": "paper_tx", "avg_price": None}
        raise RuntimeError("Live swap not enabled.")

    async def swap_usdc_to_sol(self, usdc_amount: float):
        if self.mode == "paper":
            return {"tx_id": "paper_tx", "avg_price": None}
        raise RuntimeError("Live swap not enabled.")