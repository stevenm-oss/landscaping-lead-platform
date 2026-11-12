"""Texas Yard Quotes: landing pages, lead capture, routing, contractor portal, owner dashboard, billing."""
import hmac
import logging
import os
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from functools import wraps
from zoneinfo import ZoneInfo

from flask import (Flask, Response, abort, flash, g, redirect, render_template, request, session, url_for)
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

import billing
import catalog as C
import db
import notify
import routing

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

# Templates and style.css sit next to app.py (flat layout on GitHub).
from flask import send_from_directory

app = Flask(__name__, template_folder=".", static_folder=None)


@app.get("/static/<path:filename>", endpoint="static")
def static_file(filename):
    if filename != "style.css":
        abort(404)
    return send_from_directory(app.root_path, "style.css", max_age=3600)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or "dev-only-change-me",
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),
    PERMANENT_SESSION_LIFETIME=timedelta(days=14),
    MAX_CONTENT_LENGTH=64 * 1024,
)
if os.environ.get("RENDER") and not os.environ.get("SECRET_KEY"):
    log.warning("SECRET_KEY is not set. Set it on Render before launch.")
app.teardown_appcontext(db.close)

SITE_NAME = os.environ.get("SITE_NAME", "Texas Yard Quotes")
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "")
HOUSE_NAME = os.environ.get("HOUSE_NAME", "Clean & Clear Landscape Construction")
TZ = ZoneInfo("America/Chicago")
signer = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="quote-form")
DEFAULTS = {"price_hot": 65, "price_warm": 40, "price_cold": 20, "monthly_fee": 299, "included": 15}
STATUSES = ("Contacted", "Won", "Lost", "Disputed")


# ---------- time helpers ----------
def utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def month_start():
    n = utcnow().astimezone(TZ)
    return iso(n.replace(day=1, hour=0, minute=0, second=0))


def week_ago():
    return iso(utcnow() - timedelta(days=7))


@app.template_filter("local")
def local_time(s):
    if not s:
        return ""
    dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(TZ)
    return dt.strftime("%b %-d, %-I:%M %p")


@app.template_filter("money")
def money(n):
    return "${:,}".format(int(n or 0))


# ---------- data helpers ----------
def setting(k):
    r = db.q("SELECT v FROM settings WHERE k=?", (k,), one=True)
    try:
        return int(r["v"]) if r else DEFAULTS[k]
    except ValueError:
        return DEFAULTS[k]


def set_setting(k, v):
    db.x("DELETE FROM settings WHERE k=?", (k,))
    db.x("INSERT INTO settings (k, v) VALUES (?, ?)", (k, str(v)))


def prices():
    return {"Hot": setting("price_hot"), "Warm": setting("price_warm"), "Cold": setting("price_cold")}


def contractor_rows(where="1=1", args=()):
    rows = db.q(f"SELECT * FROM contractors WHERE {where} ORDER BY is_house DESC, name", args)
    for r in rows:
        r["services_list"] = [s for s in (r["services"] or "").split(",") if s]
        r["cities_list"] = [c for c in (r["cities"] or "").split(",") if c]
    return rows


def contractor(cid):
    rows = contractor_rows("id=?", (cid,))
    return rows[0] if rows else None


def count_since(cid, since):
    return db.q("SELECT COUNT(*) AS n FROM leads WHERE contractor_id=? AND created_at>=?", (cid, since), one=True)["n"]


def event(kind, text, lead_id=None):
    db.x("INSERT INTO events (created_at, kind, text, lead_id) VALUES (?, ?, ?, ?)", (iso(utcnow()), kind, text, lead_id))


def base_url():
    return (os.environ.get("SITE_URL") or request.url_root).rstrip("/")


def client_ip():
    return (request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr or "")[:64]


_hits = defaultdict(deque)


def limited(key, limit, window):
    hits, now = _hits[key], time.time()
    while hits and hits[0] < now - window:
        hits.popleft()
    if len(hits) >= limit:
        return True
    hits.append(now)
    return False


# ---------- startup ----------
def init_app():
    with app.app_context():
        db.init_schema()
        if not db.q("SELECT id FROM contractors WHERE is_house=1", one=True):
            db.x("INSERT INTO contractors (name, email, is_house, services, cities, plan, cap, created_at) "
                 "VALUES (?, ?, 1, ?, ?, 'house', 8, ?)",
                 (HOUSE_NAME, OWNER_EMAIL or "owner@example.com", ",".join(sorted(C.CORE)),
                  "Fort Worth,Arlington,Crowley,Burleson,Keller", iso(utcnow())))
            log.info("Created house contractor %s", HOUSE_NAME)


init_app()


# ---------- security ----------
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(24)
    return session["_csrf"]


@app.before_request
def check_csrf():
    if request.method == "POST" and request.endpoint != "submit_lead":
        sent = request.form.get("_csrf", "")
        if not sent or not hmac.compare_digest(sent, session.get("_csrf", "")):
            abort(400, "Your session expired. Go back, refresh the page and try again.")


@app.after_request
def headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return resp


@app.context_processor
def inject():
    return {"site_name": SITE_NAME, "base_url": base_url(), "C": C, "csrf_token": csrf_token,
            "year":"year": utcnow().year, "gads_id": os.environ.get("GOOGLE_ADS_ID", ""), "gads_label": os.environ.get("GOOGLE_ADS_CONVERSION_LABEL", "")} utcnow().year}


def form_ctx(service_id, page):
    return {"ts": signer.dumps(int(time.time())), "vals": session.pop("form_values", {}),
            "error": session.pop("form_error", None), "service": service_id, "page": page,
            "consent": C.consent_text(SITE_NAME)}


# ---------- public pages ----------
@app.get("/")
def home():
    return render_template("home.html", form=form_ctx("sod", "/"))


@app.get("/<city_slug>/")
def city_page(city_slug):
    city = C.city_by_slug(city_slug) or abort(404)
    return render_template("city.html", city=city, form=form_ctx("sod", request.path))


@app.get("/<city_slug>/<service_slug>/")
def landing(city_slug, service_slug):
    city = C.city_by_slug(city_slug) or abort(404)
    service = C.svc_by_slug(service_slug) or abort(404)
    ld = {"@context": "https://schema.org", "@type": "Service", "name": f"{service['name']} in {city['name']}, {city['st']}",
          "serviceType": service["name"], "areaServed": {"@type": "City", "name": f"{city['name']}, {city['st']}"},
          "provider": {"@type": "Organization", "name": SITE_NAME, "url": base_url()}}
    return render_template("landing.html", city=city, service=service, lede=C.COPY[service["id"]](city), ld=ld,
                           form=form_ctx(service["id"], request.path))


@app.post("/quote")
def submit_lead():
    f = request.form
    page = f.get("page", "/")
    if not page.startswith("/") or page.startswith("//"):
        page = "/"
    # Spam checks: hidden field filled, or form sent faster than a person could fill it.
    if f.get("website"):
        return redirect(url_for("thanks"))
    try:
        started = signer.loads(f.get("ts", ""), max_age=86400)
    except BadSignature:
        started = None
    if started is None or time.time() - started < 3:
        return redirect(url_for("thanks"))

    vals = {k: (f.get(k) or "").strip() for k in ("name", "phone", "email", "zip", "service", "size", "timeline", "budget", "notes")}
    vals["consent"] = bool(f.get("consent"))
    digits = re.sub(r"\D", "", vals["phone"])
    err = None
    if limited("lead:" + client_ip(), 5, 600):
        err = "Too many quote requests from this connection. Try again in a few minutes."
    elif not vals["name"]:
        err = "Enter your name."
    elif not (len(digits) == 10 or (len(digits) == 11 and digits.startswith("1"))):
        err = "Enter a 10-digit phone number."
    elif not re.fullmatch(r"\d{5}", vals["zip"]):
        err = "Enter a 5-digit ZIP code."
    elif vals["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", vals["email"]):
        err = "Check the email address, or leave it blank."
    elif (vals["service"] not in C.SERVICE_IDS or vals["size"] not in C.SIZE
          or vals["timeline"] not in C.TIMELINE or vals["budget"] not in C.BUDGET):
        err = "Choose an answer for each question."
    if err:
        session["form_values"] = {k: v[:1000] if isinstance(v, str) else v for k, v in vals.items()}
        session["form_error"] = err
        return redirect(page + "#quote")

    city = C.city_for_zip(vals["zip"])
    score, tier = routing.score(vals["budget"], vals["timeline"], vals["size"], vals["consent"], vals["notes"], vals["email"])
    decision = routing.route(vals["service"], city, tier, contractor_rows("active=1"), count_since, prices(),
                             setting("included"), week_ago(), month_start())
    now = iso(utcnow())
    lead = db.x(
        "INSERT INTO leads (created_at, name, phone, email, zip, city, service, size, timeline, budget, notes, consent, "
        "consent_text, consent_version, ip, user_agent, page, score, tier, contractor_id, kept, price, status, route_note, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING *",
        (now, vals["name"][:80], vals["phone"][:30], vals["email"][:120], vals["zip"], city, vals["service"], vals["size"],
         vals["timeline"], vals["budget"], vals["notes"][:1000], int(vals["consent"]),
         C.consent_text(SITE_NAME) if vals["consent"] else None, C.CONSENT_VERSION if vals["consent"] else None,
         client_ip(), request.headers.get("User-Agent", "")[:300], page, score, tier, decision["contractor_id"],
         decision["kept"], decision["price"], decision["status"], decision["note"], now))
    event("lead", f"Lead #{lead['id']} ({tier} {score}) {decision['note']}", lead["id"])
    c = notify_lead(lead)
    session["thanks"] = {"first": lead["name"].split()[0], "contractor": c["name"] if c else None}
    return redirect(url_for("thanks"))


def notify_lead(lead):
    c = contractor(lead["contractor_id"]) if lead["contractor_id"] else None
    s = C.svc(lead["service"])
    first = lead["name"].split()[0]
    details = (f"{lead['name']}\nPhone: {lead['phone']}\nEmail: {lead['email'] or 'not given'}\n"
               f"Service: {s['name']}\nLocation: {lead['city'] or 'not covered'} {lead['zip']}\n"
               f"Yard: {C.SIZE[lead['size']][0]}\nWhen: {C.TIMELINE[lead['timeline']][0]}\n"
               f"Budget: {C.BUDGET[lead['budget']][0]}\nNotes: {lead['notes'] or 'none'}\n"
               f"Texting consent: {'yes' if lead['consent'] else 'no, call or email only'}\n"
               f"Score: {lead['score']} ({lead['tier']})")
    if c:
        if c["sms_alerts"] and c["phone"]:
            r = notify.sms(c["phone"], f"New {lead['tier'].lower()} lead: {s['short']} in {lead['city']}. "
                                       f"{lead['name']} {lead['phone']}. Details: {base_url()}/portal")
            event("sms", f"Text to {c['name']}: {r}", lead["id"])
        r = notify.email(c["email"], f"New lead: {s['name']} in {lead['city']}",
                         f"You have a new lead from {SITE_NAME}.\n\n{details}\n\nMark it won or lost: {base_url()}/portal")
        event("email", f"Email to {c['name']}: {r}", lead["id"])
        message = f"{c['name']} will contact you shortly about your {s['short'].lower()} project."
    else:
        r = notify.email(OWNER_EMAIL, f"Lead #{lead['id']} needs a contractor",
                         f"{lead['route_note']}.\n\n{details}\n\nAssign it: {base_url()}/admin")
        event("email", f"Owner alert for unmatched lead: {r}", lead["id"])
        message = "We’re lining up a local pro and will reach out within one business day."
    if lead["consent"]:
        r = notify.sms(lead["phone"], f"{SITE_NAME}: Thanks, {first}. {message} Reply STOP to opt out.")
        event("sms", f"Text to {first}: {r}", lead["id"])
    if lead["email"]:
        r = notify.email(lead["email"], f"Your {s['short'].lower()} quote request",
                         f"Thanks, {first}.\n\n{message}\n\n{SITE_NAME}")
        event("email", f"Email to {first}: {r}", lead["id"])
    return c


@app.get("/thanks")
def thanks():
    return render_template("thanks.html", t=session.pop("thanks", None))


@app.get("/privacy")
def privacy():
    return render_template("privacy.html")


@app.get("/terms")
def terms():
    return render_template("terms.html")


@app.get("/robots.txt")
def robots():
    return Response(f"User-agent: *\nDisallow: /portal\nDisallow: /admin\nDisallow: /quote\n"
                    f"Sitemap: {base_url()}/sitemap.xml\n", mimetype="text/plain")


@app.get("/sitemap.xml")
def sitemap():
    urls = ["/", "/privacy", "/terms"]
    for c in C.CITIES:
        urls.append(f"/{c['slug']}/")
        urls += [f"/{c['slug']}/{s['slug']}/" for s in C.SERVICES]
    body = "".join(f"<url><loc>{base_url()}{u}</loc></url>" for u in urls)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>',
                    mimetype="application/xml")


@app.get("/healthz")
def healthz():
    db.q("SELECT 1 AS ok")
    return "ok"


# ---------- contractor portal ----------
def portal_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        cid = session.get("cid")
        g.me = contractor(cid) if cid else None
        if not g.me or not g.me["active"]:
            session.pop("cid", None)
            return redirect(url_for("portal_login"))
        return fn(*a, **kw)
    return wrapper


@app.route("/portal/login", methods=["GET", "POST"])
def portal_login():
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        if limited("login:" + client_ip(), 10, 600):
            error = "Too many tries. Wait 10 minutes and try again."
        else:
            c = db.q("SELECT * FROM contractors WHERE lower(email)=? AND active=1", (email,), one=True)
            if c and c["password_hash"] and check_password_hash(c["password_hash"], pw):
                session.clear()
                session["cid"], session.permanent = c["id"], True
                return redirect(url_for("portal"))
            error = "That email and password don’t match."
    return render_template("login.html", who="Contractor sign in", action=url_for("portal_login"), email_field=True, error=error)


@app.get("/portal/logout")
def portal_logout():
    session.pop("cid", None)
    return redirect(url_for("portal_login"))


@app.get("/portal")
@portal_required
def portal():
    me = g.me
    leads = db.q("SELECT * FROM leads WHERE contractor_id=? ORDER BY created_at DESC, id DESC LIMIT 300", (me["id"],))
    won = sum(1 for l in leads if l["status"] == "Won")
    closed = sum(1 for l in leads if l["status"] in ("Won", "Lost"))
    month = [l for l in leads if l["created_at"] >= month_start()]
    owed = sum(l["price"] or 0 for l in month) + (setting("monthly_fee") if me["plan"] == "monthly" else 0)
    return render_template("portal.html", me=me, leads=leads, won=won, closed=closed, owed=owed,
                           new=sum(1 for l in leads if l["status"] == "New"), prices=prices(),
                           monthly_fee=setting("monthly_fee"), included=setting("included"),
                           used=sum(1 for l in month))


@app.post("/portal/lead/<int:lid>/status")
@portal_required
def portal_status(lid):
    val = request.form.get("status")
    if val not in STATUSES:
        abort(400)
    lead = db.q("SELECT id FROM leads WHERE id=? AND contractor_id=?", (lid, g.me["id"]), one=True) or abort(404)
    db.x("UPDATE leads SET status=?, updated_at=? WHERE id=?", (val, iso(utcnow()), lid))
    event("status", f"{g.me['name']} marked lead #{lid} {val.lower()}", lid)
    if val == "Disputed":
        notify.email(OWNER_EMAIL, f"Lead #{lid} disputed", f"{g.me['name']} reported a problem with lead #{lid}. Review it: {base_url()}/admin")
    return redirect(url_for("portal") + f"#lead-{lid}")


@app.post("/portal/settings")
@portal_required
def portal_settings():
    f = request.form
    services = [s for s in f.getlist("services") if s in C.SERVICE_IDS]
    cities = [c["name"] for c in C.CITIES if c["name"] in f.getlist("cities")]
    cap = g.me["cap"]
    if g.me["is_house"]:
        try:
            cap = max(0, min(999, int(f.get("cap", cap))))
        except ValueError:
            pass
    db.x("UPDATE contractors SET services=?, cities=?, phone=?, sms_alerts=?, paused=?, cap=? WHERE id=?",
         (",".join(services), ",".join(cities), f.get("phone", "").strip()[:30], int(bool(f.get("sms_alerts"))),
          int(bool(f.get("paused"))), cap, g.me["id"]))
    flash("Settings saved.")
    return redirect(url_for("portal") + "#settings")


@app.post("/portal/password")
@portal_required
def portal_password():
    cur, new = request.form.get("current", ""), request.form.get("new", "")
    if not check_password_hash(g.me["password_hash"] or "", cur):
        flash("Your current password didn’t match.")
    elif len(new) < 8:
        flash("Use at least 8 characters for the new password.")
    else:
        db.x("UPDATE contractors SET password_hash=? WHERE id=?", (generate_password_hash(new), g.me["id"]))
        flash("Password changed.")
    return redirect(url_for("portal") + "#settings")


# ---------- owner dashboard ----------
def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return fn(*a, **kw)
    return wrapper


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    expected = os.environ.get("ADMIN_PASSWORD", "")
    if request.method == "POST":
        if limited("admin:" + client_ip(), 8, 600):
            error = "Too many tries. Wait 10 minutes and try again."
        elif not expected:
            error = "Set ADMIN_PASSWORD on Render to turn on the dashboard."
        elif hmac.compare_digest(request.form.get("password", ""), expected):
            session.clear()
            session["admin"], session.permanent = True, True
            return redirect(url_for("admin"))
        else:
            error = "That password isn’t right."
    return render_template("login.html", who="Owner sign in", action=url_for("admin_login"), email_field=False, error=error)


@app.get("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))


@app.get("/admin")
@admin_required
def admin():
    ms = month_start()
    leads = db.q("SELECT l.*, c.name AS contractor_name, c.is_house AS house FROM leads l "
                 "LEFT JOIN contractors c ON c.id = l.contractor_id ORDER BY l.created_at DESC, l.id DESC LIMIT 200")
    month = db.q("SELECT kept, price, contractor_id, status FROM leads WHERE created_at>=?", (ms,))
    monthly = db.q("SELECT COUNT(*) AS n FROM contractors WHERE plan='monthly' AND active=1 AND is_house=0", one=True)["n"]
    revenue = sum(l["price"] or 0 for l in month if not l["kept"]) + monthly * setting("monthly_fee")
    since = iso(utcnow() - timedelta(days=90))
    gaps = {}
    for l in db.q("SELECT service, city, zip FROM leads WHERE status='Unrouted' AND created_at>=?", (since,)):
        key = f"{C.svc(l['service'])['short']} in {l['city'] or 'ZIP ' + l['zip']}"
        gaps[key] = gaps.get(key, 0) + 1
    stats = {"leads": len(month), "kept": sum(1 for l in month if l["kept"]),
             "sold": sum(1 for l in month if l["contractor_id"] and not l["kept"]),
             "unrouted": sum(1 for l in month if l["status"] == "Unrouted"), "revenue": revenue}
    return render_template("admin.html", leads=leads, stats=stats, gaps=sorted(gaps.items(), key=lambda x: -x[1]),
                           events=db.q("SELECT * FROM events ORDER BY id DESC LIMIT 40"),
                           contractors=contractor_rows("active=1"),
                           settings={k: setting(k) for k in DEFAULTS})


@app.post("/admin/settings")
@admin_required
def admin_settings():
    for k in DEFAULTS:
        try:
            set_setting(k, max(0, int(request.form.get(k, DEFAULTS[k]))))
        except ValueError:
            pass
    flash("Prices saved. They apply to the next lead.")
    return redirect(url_for("admin") + "#prices")


@app.post("/admin/lead/<int:lid>/credit")
@admin_required
def admin_credit(lid):
    lead = db.q("SELECT * FROM leads WHERE id=?", (lid,), one=True) or abort(404)
    if lead["billed_invoice"]:
        flash(f"Lead #{lid} is already on a Stripe invoice. Issue a credit note in Stripe instead.")
    else:
        db.x("UPDATE leads SET price=0, route_note=?, updated_at=? WHERE id=?",
             ((lead["route_note"] or "") + ", credited", iso(utcnow()), lid))
        event("credit", f"Lead #{lid} credited ({money(lead['price'])})", lid)
        flash(f"Lead #{lid} credited.")
    return redirect(url_for("admin"))


@app.post("/admin/lead/<int:lid>/assign")
@admin_required
def admin_assign(lid):
    lead = db.q("SELECT * FROM leads WHERE id=?", (lid,), one=True) or abort(404)
    c = contractor(request.form.get("contractor_id", type=int) or 0) or abort(400)
    if lead["contractor_id"]:
        flash(f"Lead #{lid} already went to a contractor.")
        return redirect(url_for("admin"))
    price = 0 if c["is_house"] else prices()[lead["tier"]]
    lead = db.x("UPDATE leads SET contractor_id=?, kept=?, price=?, status='New', route_note='Assigned by owner', "
                "updated_at=? WHERE id=? RETURNING *", (c["id"], c["is_house"], price, iso(utcnow()), lid))
    event("assign", f"Lead #{lid} assigned to {c['name']}", lid)
    notify_lead(lead)
    flash(f"Lead #{lid} sent to {c['name']}.")
    return redirect(url_for("admin"))


def _contractor_form():
    f = request.form
    return {
        "name": f.get("name", "").strip()[:120], "email": f.get("email", "").strip().lower()[:120],
        "phone": f.get("phone", "").strip()[:30],
        "services": ",".join(s for s in f.getlist("services") if s in C.SERVICE_IDS),
        "cities": ",".join(c["name"] for c in C.CITIES if c["name"] in f.getlist("cities")),
        "plan": f.get("plan") if f.get("plan") in ("perlead", "monthly") else "perlead",
        "sms_alerts": int(bool(f.get("sms_alerts"))), "paused": int(bool(f.get("paused"))),
        "active": int(bool(f.get("active"))), "password": f.get("password", ""),
        "cap": f.get("cap", type=int),
    }


@app.route("/admin/contractors", methods=["GET", "POST"])
@admin_required
def admin_contractors():
    if request.method == "POST":
        d = _contractor_form()
        if not d["name"] or "@" not in d["email"]:
            flash("Add a name and a valid email.")
        elif db.q("SELECT id FROM contractors WHERE lower(email)=?", (d["email"],), one=True):
            flash("A contractor with that email already exists.")
        elif len(d["password"]) < 8:
            flash("Give them a starting password of at least 8 characters.")
        else:
            db.x("INSERT INTO contractors (name, email, phone, password_hash, services, cities, plan, sms_alerts, created_at) "
                 "VALUES (?,?,?,?,?,?,?,?,?)", (d["name"], d["email"], d["phone"], generate_password_hash(d["password"]),
                                               d["services"], d["cities"], d["plan"], d["sms_alerts"], iso(utcnow())))
            event("contractor", f"Added contractor {d['name']}")
            flash(f"{d['name']} added. Send them {base_url()}/portal/login and their password.")
        return redirect(url_for("admin_contractors"))
    rows = contractor_rows()
    ms = month_start()
    for r in rows:
        r["month_leads"] = count_since(r["id"], ms)
    return render_template("admin_contractors.html", rows=rows)


@app.route("/admin/contractors/<int:cid>", methods=["GET", "POST"])
@admin_required
def admin_contractor(cid):
    c = contractor(cid) or abort(404)
    if request.method == "POST":
        d = _contractor_form()
        clash = db.q("SELECT id FROM contractors WHERE lower(email)=? AND id<>?", (d["email"], cid), one=True)
        if not d["name"] or "@" not in d["email"] or clash:
            flash("Check the name and email (each email can only be used once).")
            return redirect(url_for("admin_contractor", cid=cid))
        plan = "house" if c["is_house"] else d["plan"]
        cap = max(0, min(999, d["cap"])) if d["cap"] is not None else c["cap"]
        active = 1 if c["is_house"] else d["active"]
        db.x("UPDATE contractors SET name=?, email=?, phone=?, services=?, cities=?, plan=?, sms_alerts=?, paused=?, "
             "active=?, cap=? WHERE id=?", (d["name"], d["email"], d["phone"], d["services"], d["cities"], plan,
                                           d["sms_alerts"], d["paused"], active, cap, cid))
        if d["password"]:
            if len(d["password"]) < 8:
                flash("Password not changed: use at least 8 characters.")
            else:
                db.x("UPDATE contractors SET password_hash=? WHERE id=?", (generate_password_hash(d["password"]), cid))
        flash("Saved.")
        return redirect(url_for("admin_contractor", cid=cid))
    return render_template("admin_contractor.html", c=c)


def billing_preview():
    ym = utcnow().astimezone(TZ).strftime("%Y-%m")
    fee = setting("monthly_fee")
    out = []
    for c in contractor_rows("is_house=0 AND active=1"):
        leads = db.q("SELECT * FROM leads WHERE contractor_id=? AND billed_invoice IS NULL AND price>0 ORDER BY id", (c["id"],))
        monthly_due = c["plan"] == "monthly" and not db.q("SELECT k FROM settings WHERE k=?", (f"billed:{c['id']}:{ym}",), one=True)
        total = sum(l["price"] for l in leads) + (fee if monthly_due else 0)
        out.append({"c": c, "leads": leads, "monthly_due": monthly_due, "total": total})
    return out, ym, fee


@app.route("/admin/billing", methods=["GET", "POST"])
@admin_required
def admin_billing():
    results = []
    if request.method == "POST":
        rows, ym, fee = billing_preview()
        for r in rows:
            c = r["c"]
            if r["total"] <= 0:
                continue
            try:
                cust = c["stripe_customer"]
                if not cust:
                    cust = billing.create_customer(c["name"], c["email"], c["id"])
                    db.x("UPDATE contractors SET stripe_customer=? WHERE id=?", (cust, c["id"]))
                items = [(l["price"] * 100, f"Lead #{l['id']}: {C.svc(l['service'])['name']} in {l['city']} "
                                            f"({l['tier']}), {local_time(l['created_at'])}") for l in r["leads"]]
                if r["monthly_due"]:
                    items.append((fee * 100, f"Monthly lead plan, {ym}"))
                inv = billing.send_invoice(cust, items)
                for l in r["leads"]:
                    db.x("UPDATE leads SET billed_invoice=? WHERE id=?", (inv["id"], l["id"]))
                if r["monthly_due"]:
                    set_setting(f"billed:{c['id']}:{ym}", inv["id"])
                event("billing", f"Invoice {inv['id']} sent to {c['name']} for {money(r['total'])}")
                results.append((c["name"], True, f"Sent {money(r['total'])}", inv.get("hosted_invoice_url")))
            except billing.StripeError as e:
                results.append((c["name"], False, str(e), None))
        if not results:
            results.append(("Nothing to bill", True, "No contractor has unbilled charges.", None))
    rows, ym, fee = billing_preview()
    return render_template("admin_billing.html", rows=rows, ym=ym, results=results, stripe_on=billing.enabled())


@app.errorhandler(404)
def not_found(_e):
    return render_template("message.html", title="Page not found", text="That page doesn’t exist."), 404


@app.errorhandler(400)
def bad_request(e):
    return render_template("message.html", title="Something went wrong", text=e.description), 400
