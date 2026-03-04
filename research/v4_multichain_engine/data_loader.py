import json
from pathlib import Path
from typing import Dict, Optional
import pandas as pd


class DataLoader:
    def __init__(self, metadata_path: str = "data/metadata/asset_list.json"):
        base_dir = Path(__file__).resolve().parent
        self.metadata_path = (base_dir / metadata_path).resolve()

        if not self.metadata_path.exists():
            raise FileNotFoundError(f"Metadata file not found: {self.metadata_path}")

        with open(self.metadata_path, "r") as f:
            config = json.load(f)

        self.base_path = (base_dir / config["base_path"]).resolve()
        self.assets = config["assets"]
        self.valid_tiers = {"core", "tier1", "tier2"}

        print("DATA LOADER INITIALIZED")
        print("Base path:", self.base_path)

        # ✅ cache
        self._universe_cache: Optional[Dict[str, pd.DataFrame]] = None
        self._missing_warned: set[str] = set()

    # ==========================================================

    def load_universe(self, force_reload: bool = False) -> Dict[str, pd.DataFrame]:
        """
        Loads and caches the full universe.

        Args:
            force_reload: if True, re-read all parquet files from disk.

        Returns:
            Dict[symbol -> DataFrame]
        """
        if self._universe_cache is not None and not force_reload:
            return self._universe_cache

        universe: Dict[str, pd.DataFrame] = {}

        for symbol, meta in self.assets.items():
            if not meta.get("enabled", True):
                continue

            tier = meta.get("tier")
            if tier not in self.valid_tiers:
                raise ValueError(f"Invalid tier for {symbol}: {tier}")

            path = self._resolve_path(symbol, tier)

            if not path.exists():
                # ✅ warn once per missing symbol across entire run
                if symbol not in self._missing_warned:
                    print(f"⚠ Missing data for {symbol}")
                    self._missing_warned.add(symbol)
                continue

            df = self._load_parquet(path)
            universe[symbol] = df

        self._universe_cache = universe
        return universe

    # ==========================================================

    def _resolve_path(self, symbol: str, tier: str) -> Path:
        return self.base_path / tier / f"{symbol}_5m.parquet"

    def _load_parquet(self, path: Path) -> pd.DataFrame:
        df = pd.read_parquet(path)

        required_columns = {"timestamp", "open", "high", "low", "close"}
        missing = required_columns - set(df.columns)
        if missing:
            raise ValueError(f"Missing columns in {path.name}: {missing}")

        # force datetime (utc)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.sort_values("timestamp").reset_index(drop=True)
        return df