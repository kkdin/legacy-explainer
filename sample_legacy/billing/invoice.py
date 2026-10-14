from . import tax
from orders import OrderMgr


def make_invoice(order_id):
    m = OrderMgr()
    m.load()
    o = m.cache[order_id]
    return {"id": order_id, "total": tax.vat(o["amt"])}
