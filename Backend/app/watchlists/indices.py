"""NSE index identifiers and metadata."""

from enum import Enum


class IndexId(str, Enum):
    NIFTY_50 = "nifty50"
    NIFTY_100 = "nifty100"
    NIFTY_200 = "nifty200"
    NIFTY_500 = "nifty500"
    NSE_ALL = "nse_all"


INDEX_META: dict[IndexId, dict[str, str]] = {
    IndexId.NIFTY_50: {
        "label": "Nifty 50",
        "description": "Nifty 50 index constituents",
        "csv": "ind_nifty50list.csv",
    },
    IndexId.NIFTY_100: {
        "label": "Nifty 100",
        "description": "Nifty 100 index constituents",
        "csv": "ind_nifty100list.csv",
    },
    IndexId.NIFTY_200: {
        "label": "Nifty 200",
        "description": "Nifty 200 index constituents",
        "csv": "ind_nifty200list.csv",
    },
    IndexId.NIFTY_500: {
        "label": "Nifty 500",
        "description": "Nifty 500 index constituents",
        "csv": "ind_nifty500list.csv",
    },
    IndexId.NSE_ALL: {
        "label": "All NSE (EQ)",
        "description": "All equity-series stocks listed on NSE",
        "csv": "",
    },
}


def get_index_options() -> list[dict[str, str | bool]]:
    """Metadata for GET /api/indices."""
    return [
        {
            "id": idx.value,
            "label": meta["label"],
            "description": meta["description"],
            "slow_scan": idx == IndexId.NSE_ALL,
        }
        for idx, meta in INDEX_META.items()
    ]
