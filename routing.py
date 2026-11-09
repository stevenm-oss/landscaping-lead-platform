"""Lead scoring and routing rules."""
from catalog import CORE, SIZE, TIMELINE, BUDGET, svc


def score(budget, timeline, size, consent, notes, email):
    s = BUDGET[budget][1] + TIMELINE[timeline][1] + SIZE[size][1]
    if consent:
        s += 5
    if len((notes or "").strip()) > 20:
        s += 7
    if email:
        s += 5
    s = min(100, s)
    return s, ("Hot" if s >= 70 else "Warm" if s >= 45 else "Cold")


def _result(contractor_id=None, kept=0, price=0, status="New", note=""):
    return {"contractor_id": contractor_id, "kept": kept, "price": price, "status": status, "note": note}


def route(service, city, tier, contractors, count_since, prices, included, week_ago, month_start):
    """Pick the contractor for a lead.

    contractors: active rows with services_list / cities_list.
    count_since(contractor_id, iso_time) -> number of leads that contractor got since that time.
    """
    if not city:
        return _result(status="Unrouted", note="ZIP is outside every service area")
    cands = [c for c in contractors
             if c["active"] and not c["paused"] and service in c["services_list"] and city in c["cities_list"]]
    house = next((c for c in cands if c["is_house"]), None)
    overflow = False
    if house and service in CORE:
        if count_since(house["id"], week_ago) < house["cap"]:
            return _result(house["id"], kept=1, note=f"Kept for {house['name']}")
        overflow = True
    others = [c for c in cands if not c["is_house"]]
    if not others:
        if house:
            return _result(house["id"], kept=1, note="Over weekly capacity, but no partner covers this")
        return _result(status="Unrouted", note=f"No contractor covers {svc(service)['short'].lower()} in {city} yet")
    # Fair rotation: whoever has had the fewest leads this month goes first.
    others.sort(key=lambda c: (count_since(c["id"], month_start), c["id"]))
    pick = others[0]
    price = prices[tier]
    note = "Overflow from house account" if overflow else "Matched by service and ZIP"
    if pick["plan"] == "monthly":
        if count_since(pick["id"], month_start) < included:
            price, note = 0, note + ", included in monthly plan"
        else:
            note += ", over monthly plan"
    return _result(pick["id"], price=price, note=note)
