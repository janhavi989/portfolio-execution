"""
Broker Adapter Registry
───────────────────────
Central registry mapping broker names to their adapter classes.
Adding a new broker = add one entry here + create the adapter file.
"""
from app.adapters.base import BrokerAdapter, BrokerCredentials
from app.adapters.zerodha import ZerodhaAdapter
from app.adapters.fyers import FyersAdapter
from app.adapters.angelone import AngelOneAdapter
from app.adapters.upstox import UpstoxAdapter
from app.adapters.groww import GrowwAdapter

# Registry: broker_name → adapter class
BROKER_REGISTRY: dict[str, type[BrokerAdapter]] = {
    "zerodha": ZerodhaAdapter,
    "fyers": FyersAdapter,
    "angelone": AngelOneAdapter,
    "upstox": UpstoxAdapter,
    "groww": GrowwAdapter,
}


def get_adapter(broker: str, credentials: BrokerCredentials, paper_trading: bool = True) -> BrokerAdapter:
    """
    Factory function: returns the appropriate adapter instance for a given broker.

    Usage:
        adapter = get_adapter("zerodha", credentials, paper_trading=True)
        result = await adapter.authenticate()
    """
    adapter_class = BROKER_REGISTRY.get(broker.lower())
    if not adapter_class:
        raise ValueError(
            f"Unknown broker '{broker}'. "
            f"Supported brokers: {list(BROKER_REGISTRY.keys())}"
        )
    return adapter_class(credentials=credentials, paper_trading=paper_trading)


__all__ = [
    "BrokerAdapter", "BrokerCredentials", "get_adapter",
    "ZerodhaAdapter", "FyersAdapter", "AngelOneAdapter",
    "UpstoxAdapter", "GrowwAdapter", "BROKER_REGISTRY",
]



