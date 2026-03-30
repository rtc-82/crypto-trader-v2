from __future__ import annotations

import logging
import os
from typing import Optional

from engine.execution.base.uniswap_v3_router import UniswapV3Router, SWAP_ROUTER
from engine.execution.base.allowance_manager import AllowanceManager
from engine.execution.base.slippage_guard import SlippageGuard
from engine.execution.base.weth import WETHWrapper
from engine.execution.base.tx_signer import TxSigner
from engine.execution.base.receipt_waiter import ReceiptWaiter
from engine.execution.base.erc20 import ERC20
from engine.execution.base.base_tokens import (
    get_token_config,
    get_trade_config,
    ensure_live_ready,
)


class BaseLiveExecutor:
    """
    Symbol-aware Base executor.

    This version supports:
    - quote-token -> asset buy flows
    - asset -> quote-token sell flows

    Important:
    - In your current architecture, this is still SPOT execution.
    - A SHORT signal on Base is therefore a spot sell of the asset into quote.
    - That is NOT the same as a true borrow-based short.
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
        max_fee_gwei: int = 60,
        max_priority_gwei: int = 10,
        min_eth_reserve: float = 0.005,
        extra_gas_buffer_eth: float = 0.001,
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
        return int(self.provider.w3.eth.get_transaction_count(self.provider.address, "pending"))

    def _enforce_gas_caps(self, tx: dict) -> None:
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

    def _get_erc20_balance(self, token_address: str) -> int:
        token = ERC20(self.provider.w3, token_address)
        return int(token.balance_of(self.provider.address))

    def _enforce_token_balance_guard(self, token_address: str, required_amount: int, symbol_label: str) -> None:
        current = self._get_erc20_balance(token_address)

        self.logger.info(
            "TokenBalanceGuard: token=%s current=%s required=%s",
            symbol_label,
            current,
            required_amount,
        )

        if current < required_amount:
            raise RuntimeError(
                f"Insufficient {symbol_label} balance for execution. current={current} required={required_amount}"
            )

    # ---------------------------------------------------
    # INTERNAL EXECUTION
    # ---------------------------------------------------

    def _prepare_tx(self, tx: dict) -> dict:
        self._check_kill_switch()

        tx = dict(tx)
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

    def _build_approve_if_needed(
        self,
        token_address: str,
        required_amount: int,
        max_approve: bool,
    ) -> Optional[dict]:
        if self.allow_mgr.needs_approval(
            token_address,
            self.provider.address,
            SWAP_ROUTER,
            required_amount,
        ):
            approve_amount = (2**256 - 1) if max_approve else int(required_amount)
            return self.allow_mgr.build_approve_tx(
                token_address=token_address,
                spender=SWAP_ROUTER,
                amount=approve_amount,
                try_estimate_gas=False,
            )

        return None

    # ---------------------------------------------------
    # PUBLIC SYMBOL-AWARE EXECUTION
    # ---------------------------------------------------

    def buy_token_with_quote(
        self,
        asset_symbol: str,
        desired_token_amount: float,
        max_approve: bool = True,
    ) -> dict:
        """
        Buy asset with its configured quote token.
        Example:
            USDC -> RENDER
        """
        ensure_live_ready(asset_symbol)
        asset_cfg = get_token_config(asset_symbol)
        trade_cfg = get_trade_config(asset_symbol)

        quote_symbol = trade_cfg.get("quote_symbol", "USDC")
        fee = int(trade_cfg.get("fee", 3000))

        ensure_live_ready(quote_symbol)
        quote_cfg = get_token_config(quote_symbol)

        self.logger.info(
            "Starting BUY flow asset=%s quote=%s desired_token_amount=%s fee=%s",
            asset_symbol,
            quote_symbol,
            desired_token_amount,
            fee,
        )

        expected_quote_in = self.quoter.estimate_quote_in_for_desired_asset_out(
            asset_symbol=asset_symbol,
            desired_asset_out=desired_token_amount,
        )

        amount_in_quote_units = int(expected_quote_in * (10 ** int(quote_cfg["decimals"])))

        min_out_tokens = self.guard.min_out(float(desired_token_amount))
        min_out_token_units = int(min_out_tokens * (10 ** int(asset_cfg["decimals"])))

        if amount_in_quote_units <= 0:
            raise RuntimeError(f"Computed quote input is <= 0 for {asset_symbol}")

        if min_out_token_units <= 0:
            raise RuntimeError(f"Computed token minOut is <= 0 for {asset_symbol}")

        tx_approve = self._build_approve_if_needed(
            token_address=quote_cfg["address"],
            required_amount=amount_in_quote_units,
            max_approve=max_approve,
        )

        tx_swap = self.router.build_exact_input_single_tx(
            token_in=quote_cfg["address"],
            token_out=asset_cfg["address"],
            amount_in=amount_in_quote_units,
            min_out=min_out_token_units,
            recipient=self.provider.address,
            value_wei=0,
            try_estimate_gas=False,
            fee=fee,
        )

        planned = [t for t in [tx_approve, tx_swap] if t is not None]

        if not self.dry_run:
            self._enforce_token_balance_guard(
                token_address=quote_cfg["address"],
                required_amount=amount_in_quote_units,
                symbol_label=quote_symbol,
            )
            self._enforce_balance_guard(planned)
        else:
            self.logger.info("BalanceGuard skipped (dry_run=True)")
            self.logger.info("TokenBalanceGuard skipped (dry_run=True)")

        results: dict = {
            "asset_symbol": asset_symbol,
            "quote_symbol": quote_symbol,
            "direction": "BUY",
            "estimated_quote_in": expected_quote_in,
            "desired_token_amount": desired_token_amount,
        }

        if tx_approve is not None:
            results["approve"] = self._send_or_sign(tx_approve, f"APPROVE {quote_symbol}")

        results["swap"] = self._send_or_sign(tx_swap, f"SWAP {quote_symbol}->{asset_symbol}")

        self.logger.info("BUY flow complete for %s", asset_symbol)
        return results

    def sell_token_to_quote(
        self,
        asset_symbol: str,
        token_amount: float,
        max_approve: bool = True,
    ) -> dict:
        """
        Sell asset into its configured quote token.
        Example:
            RENDER -> USDC

        Note:
        - In your strategy engine this may be triggered for SHORT direction.
        - On-chain this is a spot sell, not a true borrow-based short.
        """
        ensure_live_ready(asset_symbol)
        asset_cfg = get_token_config(asset_symbol)
        trade_cfg = get_trade_config(asset_symbol)

        quote_symbol = trade_cfg.get("quote_symbol", "USDC")
        fee = int(trade_cfg.get("fee", 3000))

        ensure_live_ready(quote_symbol)
        quote_cfg = get_token_config(quote_symbol)

        self.logger.info(
            "Starting SELL flow asset=%s quote=%s token_amount=%s fee=%s",
            asset_symbol,
            quote_symbol,
            token_amount,
            fee,
        )

        amount_in_token_units = int(float(token_amount) * (10 ** int(asset_cfg["decimals"])))
        expected_quote_out = self.quoter.quote_asset_to_quote(
            asset_symbol=asset_symbol,
            asset_amount=token_amount,
        )
        min_out_quote = self.guard.min_out(expected_quote_out)
        min_out_quote_units = int(min_out_quote * (10 ** int(quote_cfg["decimals"])))

        if amount_in_token_units <= 0:
            raise RuntimeError(f"Computed token input is <= 0 for {asset_symbol}")

        if min_out_quote_units <= 0:
            raise RuntimeError(f"Computed quote minOut is <= 0 for {asset_symbol}")

        tx_approve = self._build_approve_if_needed(
            token_address=asset_cfg["address"],
            required_amount=amount_in_token_units,
            max_approve=max_approve,
        )

        tx_swap = self.router.build_exact_input_single_tx(
            token_in=asset_cfg["address"],
            token_out=quote_cfg["address"],
            amount_in=amount_in_token_units,
            min_out=min_out_quote_units,
            recipient=self.provider.address,
            value_wei=0,
            try_estimate_gas=False,
            fee=fee,
        )

        planned = [t for t in [tx_approve, tx_swap] if t is not None]

        if not self.dry_run:
            self._enforce_token_balance_guard(
                token_address=asset_cfg["address"],
                required_amount=amount_in_token_units,
                symbol_label=asset_symbol,
            )
            self._enforce_balance_guard(planned)
        else:
            self.logger.info("BalanceGuard skipped (dry_run=True)")
            self.logger.info("TokenBalanceGuard skipped (dry_run=True)")

        results: dict = {
            "asset_symbol": asset_symbol,
            "quote_symbol": quote_symbol,
            "direction": "SELL",
            "expected_quote_out": expected_quote_out,
            "token_amount": token_amount,
        }

        if tx_approve is not None:
            results["approve"] = self._send_or_sign(tx_approve, f"APPROVE {asset_symbol}")

        results["swap"] = self._send_or_sign(tx_swap, f"SWAP {asset_symbol}->{quote_symbol}")

        self.logger.info("SELL flow complete for %s", asset_symbol)
        return results

    # ---------------------------------------------------
    # BACKWARD-COMPAT SHIM
    # ---------------------------------------------------

    def execute_weth_to_usdc(
        self,
        weth_amount_eth: float,
        wrap_eth_first: bool = True,
        max_approve: bool = True,
    ) -> dict:
        """
        Kept only so older code paths do not explode immediately.
        """
        self.logger.info(
            "Legacy execute_weth_to_usdc() called. Prefer symbol-aware methods instead."
        )

        tx_wrap: Optional[dict] = None
        tx_approve: Optional[dict] = None

        from engine.execution.base.base_tokens import get_token_config

        weth_cfg = get_token_config("WETH")
        usdc_cfg = get_token_config("USDC")

        amount_in_wei = int(weth_amount_eth * 10**18)

        if wrap_eth_first:
            tx_wrap = self.weth.build_wrap_tx(
                amount_eth=weth_amount_eth,
                try_estimate_gas=False,
            )

        expected_usdc = self.quoter.quote_asset_to_quote("WETH", weth_amount_eth)
        min_usdc = self.guard.min_out(expected_usdc)
        min_out_usdc_units = int(min_usdc * (10 ** int(usdc_cfg["decimals"])))

        if self.allow_mgr.needs_approval(
            weth_cfg["address"],
            self.provider.address,
            SWAP_ROUTER,
            amount_in_wei,
        ):
            approve_amount = (2**256 - 1) if max_approve else amount_in_wei
            tx_approve = self.allow_mgr.build_approve_tx(
                token_address=weth_cfg["address"],
                spender=SWAP_ROUTER,
                amount=approve_amount,
                try_estimate_gas=False,
            )

        tx_swap = self.router.build_exact_input_single_tx(
            token_in=weth_cfg["address"],
            token_out=usdc_cfg["address"],
            amount_in=amount_in_wei,
            min_out=min_out_usdc_units,
            recipient=self.provider.address,
            try_estimate_gas=False,
            fee=3000,
        )

        planned = [t for t in [tx_wrap, tx_approve, tx_swap] if t is not None]
        if not self.dry_run:
            self._enforce_balance_guard(planned)
        else:
            self.logger.info("BalanceGuard skipped (dry_run=True)")

        results: dict = {}

        if tx_wrap is not None:
            results["wrap"] = self._send_or_sign(tx_wrap, "WRAP")

        if tx_approve is not None:
            results["approve"] = self._send_or_sign(tx_approve, "APPROVE")

        results["swap"] = self._send_or_sign(tx_swap, "SWAP")

        self.logger.info("Legacy execution flow complete")
        return results