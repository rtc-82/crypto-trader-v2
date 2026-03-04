from web3 import Web3
import os
from dotenv import load_dotenv


def test_connection():
    load_dotenv()

    rpc_url = os.getenv("BASE_RPC_URL")
    private_key = os.getenv("BASE_PRIVATE_KEY")

    if not rpc_url or not private_key:
        print("Missing BASE_RPC_URL or BASE_PRIVATE_KEY in .env")
        return

    w3 = Web3(Web3.HTTPProvider(rpc_url))

    if not w3.is_connected():
        print("Failed to connect to Base RPC.")
        return

    account = w3.eth.account.from_key(private_key)

    chain_id = w3.eth.chain_id
    balance_wei = w3.eth.get_balance(account.address)
    balance_eth = w3.from_wei(balance_wei, "ether")

    print("\n=== BASE CONNECTION SUCCESS ===")
    print(f"Chain ID: {chain_id}")
    print(f"Wallet Address: {account.address}")
    print(f"Balance (ETH): {balance_eth}")
    print("\nExpected Chain ID for Base Mainnet: 8453\n")


if __name__ == "__main__":
    test_connection()