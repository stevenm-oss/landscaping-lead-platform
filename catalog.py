"""Services, cities, page copy and form options. Edit this file to add cities or services."""
import re


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


SERVICES = [
    {"id": "sod", "name": "Sod installation", "short": "Sod", "slug": "sod-installation"},
    {"id": "flowerbeds", "name": "Flowerbed installation", "short": "Flowerbeds", "slug": "flowerbed-installation"},
    {"id": "irrigation", "name": "Sprinkler repair", "short": "Irrigation", "slug": "sprinkler-repair"},
    {"id": "fencing", "name": "Wood fence installation", "short": "Wood fencing", "slug": "wood-fence-installation"},
    {"id": "hardscape", "name": "Patios and hardscape", "short": "Hardscape", "slug": "patios-and-hardscape"},
    {"id": "drainage", "name": "Yard drainage", "short": "Drainage", "slug": "yard-drainage"},
    {"id": "lighting", "name": "Landscape lighting", "short": "Lighting", "slug": "landscape-lighting"},
    {"id": "lawncare", "name": "Lawn care", "short": "Lawn care", "slug": "lawn-care"},
    {"id": "tree", "name": "Tree trimming", "short": "Tree service", "slug": "tree-trimming"},
]
SERVICE_IDS = {s["id"] for s in SERVICES}

# Services the house account (Clean & Clear) keeps inside its own cities.
CORE = {"sod", "flowerbeds", "irrigation", "fencing"}

_CITIES = [
    ("Fort Worth", "TX", "heavy clay over limestone",
     ["76102", "76103", "76104", "76105", "76106", "76107", "76108", "76109", "76110", "76111", "76112",
      "76114", "76115", "76116", "76117", "76118", "76119", "76120", "76123", "76126", "76129", "76131",
      "76132", "76133", "76134", "76135", "76137", "76140", "76148", "76155", "76164", "76177", "76179"]),
    ("Arlington", "TX", "dense clay that holds water",
     ["76001", "76002", "76006", "76010", "76011", "76012", "76013", "76014", "76015", "76016", "76017", "76018"]),
    ("Crowley", "TX", "heavy clay over limestone", ["76036"]),
    ("Burleson", "TX", "rocky clay", ["76028", "76097"]),
    ("Keller", "TX", "sandy loam over clay", ["76244", "76248"]),
    ("Dallas", "TX", "Blackland Prairie clay", []),  # all 752xx ZIPs, see city_for_zip
    ("Plano", "TX", "Blackland Prairie clay", ["75023", "75024", "75025", "75026", "75074", "75075", "75093", "75094"]),
    ("Frisco", "TX", "Blackland Prairie clay", ["75033", "75034", "75035", "75036"]),
    ("Denton", "TX", "sandy loam and clay", ["76201", "76205", "76207", "76208", "76209", "76210"]),
    ("Austin", "TX", "thin soil over limestone", []),  # all 787xx ZIPs
    ("Oklahoma City", "OK", "red clay", []),  # all 731xx ZIPs
]
CITIES = [{"name": n, "st": st, "soil": soil, "zips": set(z), "slug": slugify(f"{n} {st}")}
          for n, st, soil, z in _CITIES]
_PREFIX = {"761": "Fort Worth", "752": "Dallas", "787": "Austin", "731": "Oklahoma City"}


def city_for_zip(z):
    for c in CITIES:
        if z in c["zips"]:
            return c["name"]
    return _PREFIX.get(z[:3])


def svc(service_id):
    return next((s for s in SERVICES if s["id"] == service_id), None)


def svc_by_slug(slug):
    return next((s for s in SERVICES if s["slug"] == slug), None)


def city_by_slug(slug):
    return next((c for c in CITIES if c["slug"] == slug), None)


def _heat(c):
    return "Oklahoma" if c["st"] == "OK" else "Texas"


COPY = {
    "sod": lambda c: f"New grass in {c['name']} has to root into {c['soil']} and make it through August. Local crews grade, prep and lay St. Augustine, Bermuda or Zoysia matched to your sun and shade.",
    "flowerbeds": lambda c: f"Beds that look good in April and still look good in July. {c['name']} pros amend {c['soil']}, cut clean edges and plant natives that handle {_heat(c)} heat.",
    "irrigation": lambda c: f"Dry spots and high water bills usually trace back to the system. {c['name']} techs find leaks, fix zones and set schedules that follow local watering rules.",
    "fencing": lambda c: f"Cedar and pine privacy fences with posts set deep enough for {c['soil']}, so they stay straight when the ground shifts.",
    "hardscape": lambda c: f"Patios, walkways and retaining walls on a base built for {c['soil']}, so pavers don’t heave or sink.",
    "drainage": lambda c: f"Standing water after a storm is a {c['soil']} problem. Local pros install French drains, regrade and move water away from your foundation.",
    "lighting": lambda c: f"Low-voltage path, uplight and patio lighting that makes your {c['name']} yard usable after dark.",
    "lawncare": lambda c: f"Mowing, edging and seasonal treatments from crews who already work your part of {c['name']}.",
    "tree": lambda c: f"Trimming, removal and storm cleanup by experienced crews who know {c['name']}’s live oaks, cedar elms and pecans.",
}

# (label, score points)
SIZE = {"small": ("Small (under 5,000 sq ft)", 5), "medium": ("Average (5,000–10,000 sq ft)", 10),
        "large": ("Large (10,000 sq ft to 1 acre)", 15), "acre": ("Over an acre", 18)}
TIMELINE = {"asap": ("As soon as possible", 30), "month": ("Within a month", 22),
            "quarter": ("In 1–3 months", 12), "research": ("Just getting prices", 3)}
BUDGET = {"u1": ("Under $1,000", 5), "b1": ("$1,000–$3,000", 15), "b3": ("$3,000–$7,500", 25),
          "b7": ("$7,500–$15,000", 30), "b15": ("$15,000+", 35)}

CONSENT_VERSION = "2026-11-v1"


def consent_text(site_name):
    return (f"I agree to receive calls and texts about my project from {site_name} and the contractor it "
            "matches me with, at the number above, including automated texts. Consent isn’t required to get "
            "a quote. Message frequency varies. Message and data rates may apply. Reply STOP to opt out or "
            "HELP for help.")
