import orders
from utils import fmt_money


def weekly(limit=100):
    lines = []
    for k, amt in orders.get_open(limit):
        lines.append(str(k) + ": " + fmt_money(amt))
    return "\n".join(lines)
