from models.signal import Signal


class SimpleResearchEngine:

    def generate_signal(self) -> Signal | None:
        """
        For now: always generates a test Solana signal.
        Later this becomes your real research layer.
        """

        return Signal(
            chain="solana",
            action="buy",
            token_in="So11111111111111111111111111111111111111112",
            token_out="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            confidence=0.8,
            expected_edge=0.02,
            risk_score=0.3,
            strategy_name="simple_test_strategy",
        )