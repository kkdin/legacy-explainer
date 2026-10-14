import sqlite3

DB = "shop.db"


def get_conn():
    return sqlite3.connect(DB)


def q(sql, args=()):
    c = get_conn()
    cur = c.cursor()
    cur.execute(sql, args)
    rows = cur.fetchall()
    c.close()
    return rows
