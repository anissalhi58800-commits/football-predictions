import os, json, math, time, requests
from datetime import datetime, timezone

B = "https://api.football-data.org/v4"
H = {"X-Auth-Token": os.environ["FD_API_KEY"]}


def get(path, **params):
    for _ in range(4):
        r = requests.get(B + path, headers=H, params=params, timeout=30)
        if r.status_code == 429:  # حد الطلبات: ننتظر دقيقة
            time.sleep(65)
            continue
        r.raise_for_status()
        return r.json()
    return {}


def pois(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def predict(lh, la):
    ph = pd = pa = 0.0
    best = (0, 0, 0.0)
    for i in range(9):
        for j in range(9):
            p = pois(i, lh) * pois(j, la)
            if i > j: ph += p
            elif i == j: pd += p
            else: pa += p
            if p > best[2]: best = (i, j, p)
    s = ph + pd + pa
    return ph / s, pd / s, pa / s, best[0], best[1]


def build_model(played):
    t, hg, ag, n = {}, 0, 0, 0
    for m in played:
        h, a = m["score"]["fullTime"]["home"], m["score"]["fullTime"]["away"]
        if h is None or a is None:
            continue
        hg += h; ag += a; n += 1
        for tid, gf, ga in ((m["homeTeam"]["id"], h, a), (m["awayTeam"]["id"], a, h)):
            d = t.setdefault(tid, [0, 0, 0])
            d[0] += gf; d[1] += ga; d[2] += 1
    avg_h = hg / n if n else 1.5
    avg_a = ag / n if n else 1.2
    avg = (avg_h + avg_a) / 2
    k = 3  # تقليل تأثير العينات الصغيرة

    def strength(tid):
        gf, ga, c = t.get(tid, [0, 0, 0])
        return ((gf + k * avg) / (c + k)) / avg, ((ga + k * avg) / (c + k)) / avg

    return strength, avg_h, avg_a


today = get("/matches").get("matches", [])
models, out = {}, []

for m in today:
    code = m["competition"]["code"]
    if code not in models:
        time.sleep(7)  # الخطة المجانية: 10 طلبات بالدقيقة
        try:
            data = get(f"/competitions/{code}/matches", status="FINISHED")
            models[code] = build_model(data.get("matches", []))
        except Exception:
            models[code] = build_model([])
    strength, avg_h, avg_a = models[code]
    att_h, def_h = strength(m["homeTeam"]["id"])
    att_a, def_a = strength(m["awayTeam"]["id"])
    ph, pd, pa, gh, ga = predict(avg_h * att_h * def_a, avg_a * att_a * def_h)
    ft = m["score"]["fullTime"]
    out.append({
        "league": m["competition"]["name"],
        "time": m["utcDate"],
        "status": m["status"],
        "home": m["homeTeam"].get("shortName") or m["homeTeam"]["name"],
        "away": m["awayTeam"].get("shortName") or m["awayTeam"]["name"],
        "crest_h": m["homeTeam"].get("crest"),
        "crest_a": m["awayTeam"].get("crest"),
        "p": [round(ph * 100), round(pd * 100), round(pa * 100)],
        "score": [gh, ga],
        "result": None if ft["home"] is None else [ft["home"], ft["away"]],
    })

out.sort(key=lambda x: (x["league"], x["time"]))
with open("predictions.json", "w", encoding="utf-8") as f:
    json.dump({"updated": datetime.now(timezone.utc).isoformat(), "matches": out},
              f, ensure_ascii=False)
print(f"تم: {len(out)} مباراة")
