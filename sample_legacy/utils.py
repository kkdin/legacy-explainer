def proc(d, t):
    r = []
    for k in d:
        if d[k]["status"] == "A" and d[k]["amt"] > t:
            r.append((k, d[k]["amt"] * 1.21))
    r.sort(key=lambda x: x[1], reverse=True)
    return r


def fmt_money(x):
    return "EUR " + str(round(x, 2))
