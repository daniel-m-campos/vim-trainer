"""Inventory helpers used as a fixture for the template tests."""

import logging
import collections

logger = logging.getLogger("inventory")
DEFAULT_LIMIT = 25  # maximum number of items per page


def summarize(items, limit=10, sep=", "):
    """Return a printable summary of the items.

    The summary lists at most `limit` names.
    """
    names = [item["name"] for item in items]
    counts = collections.Counter(names)
    if len(names) > limit:
        logger.warning("truncating %s items", len(names))
        names = names[:limit]
    names = sorted(names, key=str.lower, reverse=True)
    labels = {"total": len(items), "unique": len(counts)}
    result = sep.join(names)  # joined for display
    return f"{result} ({labels['total']} total)"


def restock(inventory, item, amount):
    inventory.setdefault(item, 0)
    inventory[item] += amount
    if inventory[item] > DEFAULT_LIMIT:
        inventory[item] = DEFAULT_LIMIT
    logger.info("restocked %s to %d", item, inventory[item])
    return inventory
