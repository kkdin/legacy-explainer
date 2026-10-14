"""Order handling for the old shop system."""
from db import q
import utils


class OrderMgr:
    def __init__(self):
        self.cache = {}

    def load(self):
        for row in q("SELECT id, status, amt FROM orders"):
            self.cache[row[0]] = {"status": row[1], "amt": row[2]}

    def big_active(self, limit):
        return utils.proc(self.cache, limit)


def get_open(t):
    m = OrderMgr()
    m.load()
    return m.big_active(t)
