from __future__ import annotations

import logging
import os
from typing import Optional

from engine.execution.base.uniswap_v3_router import UniswapV3Router, SWAP_ROUTER, WETH
from engine.execution.base.allowance_manager import AllowanceManager
from engine.execution.base.slippage_guard import SlippageGuard
from engine.execution.base.weth import WETHWrapper
from engine.execution.base.tx_signer import TxSigner
from engine.execution.base.receipt_waiter import ReceiptWaiter


class BaseLiveExecutor:
    """
    Executes:
        1) Optional ETH -> WETH wrap
        2) Optional ERC20 approve
        3) Swap via Uniswap V3

    Hardening:
        - dry_run default True
        - Gas cap protection (maxFeePerGas / maxPriorityFeePerGas / gasPrice)
        - ETH balance guard (reserve + worst-case tx costs)
        - Nonce refresh (pending nonce) before each sign/send
        - Optional kill-switch file
    """

    def __init__(
        self,
        provider,
        quoter,
        logger: logging.Logger,
        slippage_bps: int = 50,
        fee: int = 3000,
        dry_run: bool = True,
        kill_switch_path: str = "KILL_SWITCH",
        # ---- Safety caps ----
        max_fee_gwei: int = 60,          # hard cap for maxFeePerGas
        max_priority_gwei: int = 10,     # hard cap for maxPriorityFeePerGas
        # ---- Balance guard ----
        min_eth_reserve: float = 0.005,      # keep at least this much ETH unspent
        extra_gas_buffer_eth: float = 0.001, # extra cushion for fee volatility
    ):
        self.provider = provider
        self.quoter = quoter
        self.logger = logger
        self.dry_run = dry_run
        self.kill_switch_path = kill_switch_path

        self.guard = SlippageGuard(logger, slippage_bps=slippage_bps)
        self.router = UniswapV3Router(provider, logger, fee=fee)
        self.allow_mgr = AllowanceManager(provider, logger)
        self.weth = WETHWrapper(provider, logger)
        self.signer = TxSigner(provider, logger)
        self.waiter = ReceiptWaiter(provider, logger)

        self.max_fee_wei = int(max_fee_gwei) * 10**9
        self.max_priority_wei = int(max_priority_gwei) * 10**9

        self.min_eth_reserve = float(min_eth_reserve)
        self.extra_gas_buffer_eth = float(extra_gas_buffer_eth)

    # ---------------------------------------------------
    # INTERNAL SAFETY
    # ---------------------------------------------------

    def _check_kill_switch(self) -> None:
        if os.path.exists(self.kill_switch_path):
            raise RuntimeError("Kill switch detected. Execution halted.")

    def _pending_nonce(self) -> int:
        # Use pending nonce so sequential broadcasts won't collide.
        return int(self.provider.w3.eth.get_transaction_count(self.provider.address, "pending"))

    def _enforce_gas_caps(self, tx: dict) -> None:
        # EIP-1559 path
        if "maxFeePerGas" in tx:
            max_fee = int(tx["maxFeePerGas"])
            if max_fee > self.max_fee_wei:
                raise RuntimeError(
                    f"Gas cap hit: maxFeePerGas={max_fee} > cap={self.max_fee_wei} wei"
                )

        if "maxPriorityFeePerGas" in tx:
            prio = int(tx["maxPriorityFeePerGas"])
            if prio > self.max_priority_wei:
                raise RuntimeError(
                    f"Gas cap hit: maxPriorityFeePerGas={prio} > cap={self.max_priority_wei} wei"
                )

        # Legacy path
        if "gasPrice" in tx:
            gp = int(tx["gasPrice"])
            if gp > self.max_fee_wei:
                raise RuntimeError(
                    f"Gas cap hit: gasPrice={gp} > cap={self.max_fee_wei} wei"
                )

    def _tx_max_cost_eth(self, tx: dict) -> float:
        gas = int(tx.get("gas", 0))
        if gas <= 0:
            return 0.0

        if "maxFeePerGas" in tx:
            per_gas = int(tx["maxFeePerGas"])
        elif "gasPrice" in tx:
            per_gas = int(tx["gasPrice"])
        else:
            # If fees aren't present, assume worst = cap
            per_gas = self.max_fee_wei

        value_wei = int(tx.get("value", 0))
        total_wei = value_wei + gas * per_gas
        return total_wei / 10**18

    def _enforce_balance_guard(self, planned_txs: list[dict]) -> None:
        bal = float(self.provider.get_balance_eth())

        planned_cost = sum(self._tx_max_cost_eth(t) for t in planned_txs)
        required = self.min_eth_reserve + planned_cost + self.extra_gas_buffer_eth

        self.logger.info(
            f"BalanceGuard: balance={bal:.6f} ETH | planned_cost≈{planned_cost:.6f} ETH "
            f"| reserve={self.min_eth_reserve:.6f} ETH | buffer={self.extra_gas_buffer_eth:.6f} ETH "
            f"| required≈{required:.6f} ETH"
        )

        if bal < required:
            raise RuntimeError(
                f"Insufficient ETH for safe execution. balance={bal:.6f} < required≈{required:.6f}"
            )

    # ---------------------------------------------------
    # INTERNAL EXECUTION
    # ---------------------------------------------------

    def _prepare_tx(self, tx: dict) -> dict:
        """
        Refresh nonce and enforce gas caps before signing/sending.
        """
        self._check_kill_switch()

        tx = dict(tx)  # copy
        tx["nonce"] = self._pending_nonce()
        self._enforce_gas_caps(tx)
        return tx

    def _send_or_sign(self, tx: dict, label: str) -> str:
        tx = self._prepare_tx(tx)

        signed = self.signer.sign(tx)
        tx_hash = signed.hash.hex()
        self.logger.info(f"{label} signed: {tx_hash}")

        if self.dry_run:
            self.logger.info(f"{label} dry_run=True (not broadcast)")
            return tx_hash

        sent_hash = self.signer.send(signed)
        self.logger.info(f"{label} broadcast: {sent_hash}")

        receipt = self.waiter.wait(sent_hash)
        status = receipt.get("status")
        self.logger.info(f"{label} receipt status: {status}")

        if status != 1:
            raise RuntimeError(f"{label} failed on-chain: {sent_hash}")

        return sent_hash

    # ---------------------------------------------------
    # PUBLIC EXECUTION
    # ---------------------------------------------------

    def execute_weth_to_usdc(
        self,
        weth_amount_eth: float,
        wrap_eth_first: bool = True,
        max_approve: bool = True,
    ) -> dict:
        """
        Returns dict of tx hashes.
        In dry_run mode, only signs and returns hashes.
        """
        self.logger.info("Starting WETH -> USDC execution flow")

        tx_wrap: Optional[dict] = None
        tx_approve: Optional[dict] = None

        amount_in_wei = int(weth_amount_eth * 10**18)

        # 1) Optional wrap
        if wrap_eth_first:
            tx_wrap = self.weth.build_wrap_tx(
                amount_eth=weth_amount_eth,
                try_estimate_gas=False,
            )

        # 2) Quote + slippage
        expected_usdc = self.quoter.quote_weth_to_usdc(weth_amount_eth)
        min_usdc = self.guard.min_out(expected_usdc)
        min_out_usdc_units = int(min_usdc * 10**6)

        # 3) Approve if needed
        if self.allow_mgr.needs_approval(WETH, self.provider.address, SWAP_ROUTER, amount_in_wei):
            approve_amount = (2**256 - 1) if max_approve else amount_in_wei
            tx_approve = self.allow_mgr.build_approve_tx(
                token_address=WETH,
                spender=SWAP_ROUTER,
                amount=approve_amount,
                try_estimate_gas=False,
            )

        # 4) Swap
        tx_swap = self.router.build_weth_to_usdc_tx(
            amount_in_wei=amount_in_wei,
            min_out_usdc=min_out_usdc_units,
            recipient=self.provider.address,
            try_estimate_gas=False,
        )

        # Balance guard: enforce only when broadcasting
        planned = [t for t in [tx_wrap, tx_approve, tx_swap] if t is not None]
        if not self.dry_run:
            self._enforce_balance_guard(planned)
        else:
            self.logger.info("BalanceGuard skipped (dry_run=True)")

        # Execute in sequence
        results: dict = {}

        if tx_wrap is not None:
            results["wrap"] = self._send_or_sign(tx_wrap, "WRAP")

        if tx_approve is not None:
            results["approve"] = self._send_or_sign(tx_approve, "APPROVE")

        results["swap"] = self._send_or_sign(tx_swap, "SWAP")

        self.logger.info("Execution flow complete")
        return results