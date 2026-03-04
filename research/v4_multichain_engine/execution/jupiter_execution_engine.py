# execution/jupiter_execution_engine.py

import httpx


class JupiterExecutionEngine:
    def __init__(self, api_key: str, dry_run: bool):
        self.api_key = api_key
        self.dry_run = dry_run
        self.base_url = "https://quote-api.jup.ag/v6/quote"

    async def execute_swap(self, token_in: str, token_out: str, amount: int):

        if self.dry_run:
            return {
                "success": True,
                "price": 1.0,
            }

        params = {
            "inputMint": token_in,
            "outputMint": token_out,
            "amount": amount,
            "slippageBps": 50,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                self.base_url,
                params=params,
                headers=headers,
            )

        response.raise_for_status()
        data = response.json()

        out_amount = int(data["data"][0]["outAmount"])

        return {
            "success": True,
            "price": out_amount / amount if amount else 0,
        }