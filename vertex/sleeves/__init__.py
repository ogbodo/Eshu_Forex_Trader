"""Sleeve package — importing it registers all available sleeves."""

from vertex.sleeves.base import REGISTRY, Sleeve, positions_from_raw, register  # noqa: F401
from vertex.sleeves import slow_trend  # noqa: F401  (registers "slow_trend")
from vertex.sleeves import fast_trend  # noqa: F401  (registers "fast_trend")
from vertex.sleeves import xsect       # noqa: F401  (registers "xsect")


def build(name, **kw):
    """Instantiate a registered sleeve by name."""
    if name not in REGISTRY:
        raise KeyError(f"unknown sleeve {name!r}; have {sorted(REGISTRY)}")
    return REGISTRY[name](**kw)
