# execution/live_executor_adapter.py
from __future__ import annotations

from typing import Any, Dict, Optional

from research.v4_multichain_engine.models.signal import Signal
from research.v4_multichain_engine.execution.abstract_executor import AbstractExecutor  # :contentReference[oaicite:5]{index=5}


class LiveExecutorAdapter(AbstractExecutor):
    """
    Wrap your battle-tested production executor so the orchestration layer depends only on AbstractExecutor.

    You should NOT put risk logic here.
    You should NOT put strategy logic here.
    This is purely a compatibility wrapper.
    """

    def __init__(self, production_executor: Any, mode: str = "paper"):
        """
        Args:
            production_executor: your existing ProductionSolanaExecutor instance (or multi-executor).
            mode: "paper" or "live"
        """
        self._exec = production_executor
        self.mode = mode

    async def execute_trade(self, signal: Signal, amount: int) -> Dict[str, Any]:
        """
        Standard execution entrypoint.

        Expects:
          - signal.chain == "solana" for now
          - amount = lamports or base units you choose for your executor

        Returns dict with:
          {
            "success": bool,
            "tx_signature": str|None,
            "error": str|None,
            "meta": dict
          }
        """
        # Attach amount for traceability
        signal = Signal(**{**signal.__dict__, "amount_lamports": int(amount)})

        # --- PAPER MODE: do not send tx ---
        if self.mode == "paper":
            return {
                "success": True,
                "tx_signature": None,
                "error": None,
                "meta": {
                    "paper": True,
                    "chain": signal.chain,
                    "action": signal.action,
                    "token_in": signal.token_in,
                    "token_out": signal.token_out,
                    "amount": int(amount),
                },
            }

        # --- LIVE MODE: call your real production executor ---
        # IMPORTANT: Replace this call with the method your executor actually exposes.
        # Example possibilities:
        #   await self._exec.swap(token_in=..., token_out=..., amount=..., slippage_bps=...)
        #   await self._exec.execute(signal)
        #
        # Keep it minimal and deterministic.
        try:
            result = await self._exec.execute_trade(signal=signal, amount=int(amount))
            # normalize
            return {
                "success": bool(result.get("success", False)),
                "tx_signature": result.get("tx_signature"),
                "error": result.get("error"),
                "meta": result.get("meta", {}),
            }
        except Exception as e:
            return {
                "success": False,
                "tx_signature": None,
                "error": f"{type(e).__name__}: {e}",
                "meta": {},
            }