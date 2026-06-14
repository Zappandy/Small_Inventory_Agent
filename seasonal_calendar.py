"""
Indian festival & seasonal demand calendar.
Covers South India focus (Andhra Pradesh / Telangana) with all-India events.
Returns context used by the LangGraph agent for demand prediction.
"""

import datetime
from dataclasses import dataclass, field


@dataclass
class Festival:
    key: str
    name: str
    name_te: str
    months: list[int]          # calendar months it falls in
    region: str                 # "all", "south", "north", "west", "east"
    demand_items: list[str]     # English product names / categories
    demand_multiplier: float    # expected demand spike vs normal week
    prep_days: int              # how many days ahead to start stocking
    tips: str                   # stocking tip for the shopkeeper


FESTIVALS: list[Festival] = [
    Festival(
        key="pongal",
        name="Pongal / Makar Sankranti",
        name_te="పొంగల్ / మకర సంక్రాంతి",
        months=[1],
        region="south",
        demand_items=["Rice Basmati", "Jaggery", "Sesame Seeds", "Coconut",
                      "Desi Ghee", "Turmeric Powder", "Sugar"],
        demand_multiplier=3.0,
        prep_days=10,
        tips="Stock extra rice, jaggery, sesame seeds, and coconuts 10 days before Jan 14."
             " Pongal dish ingredients (rice + jaggery + ghee) see 3× spike in AP/Telangana.",
    ),
    Festival(
        key="republic_day",
        name="Republic Day",
        name_te="గణతంత్ర దినోత్సవం",
        months=[1],
        region="all",
        demand_items=["Snacks & Biscuits", "Beverages"],
        demand_multiplier=1.2,
        prep_days=2,
        tips="Minor bump in snacks and soft drinks around Jan 26.",
    ),
    Festival(
        key="maha_shivaratri",
        name="Maha Shivaratri",
        name_te="మహా శివరాత్రి",
        months=[2, 3],
        region="all",
        demand_items=["Milk", "Coconut", "Banana", "Desi Ghee", "Tamarind"],
        demand_multiplier=1.8,
        prep_days=5,
        tips="Devotees fast and offer milk & fruits. Dairy and fresh fruit spike.",
    ),
    Festival(
        key="ugadi",
        name="Ugadi (Telugu New Year)",
        name_te="ఉగాది",
        months=[3, 4],
        region="south",
        demand_items=["Jaggery", "Tamarind", "Coconut", "Banana", "Curd",
                      "Turmeric Powder", "Desi Ghee", "Sesame Seeds"],
        demand_multiplier=3.5,
        prep_days=7,
        tips="Ugadi Pachadi requires neem, jaggery, tamarind, raw mango — stock ALL of these."
             " Biggest AP/Telangana festival: expect 3.5× sales across pantry items.",
    ),
    Festival(
        key="holi",
        name="Holi",
        name_te="హోలీ",
        months=[3],
        region="all",
        demand_items=["Sugar", "Milk", "Coconut", "Snacks & Biscuits"],
        demand_multiplier=2.0,
        prep_days=5,
        tips="Sweets and milk see 2× demand across India.",
    ),
    Festival(
        key="ram_navami",
        name="Ram Navami",
        name_te="రామ నవమి",
        months=[4],
        region="all",
        demand_items=["Coconut", "Banana", "Jaggery", "Desi Ghee"],
        demand_multiplier=1.6,
        prep_days=4,
        tips="Prasad ingredients (coconut, jaggery, banana) see steady spike.",
    ),
    Festival(
        key="eid_ul_fitr",
        name="Eid ul-Fitr",
        name_te="ఈద్ ఉల్ ఫిత్ర్",
        months=[3, 4, 5],   # varies year to year
        region="all",
        demand_items=["Rice Basmati", "Sugar", "Desi Ghee", "Coconut",
                      "Milk", "Snacks & Biscuits"],
        demand_multiplier=2.5,
        prep_days=5,
        tips="Seviyan (vermicelli), rice, ghee and sweets see strong demand.",
    ),
    Festival(
        key="bonalu",
        name="Bonalu",
        name_te="బోనాలు",
        months=[7, 8],
        region="south",
        demand_items=["Rice Basmati", "Jaggery", "Coconut", "Turmeric Powder",
                      "Desi Ghee", "Curd"],
        demand_multiplier=2.5,
        prep_days=6,
        tips="Telangana festival — bonam (rice + jaggery + curd) offering ingredients spike sharply.",
    ),
    Festival(
        key="independence_day",
        name="Independence Day",
        name_te="స్వాతంత్ర్య దినోత్సవం",
        months=[8],
        region="all",
        demand_items=["Snacks & Biscuits", "Beverages"],
        demand_multiplier=1.3,
        prep_days=2,
        tips="Minor snack and beverage bump around Aug 15.",
    ),
    Festival(
        key="onam",
        name="Onam",
        name_te="ఓణం",
        months=[8, 9],
        region="south",
        demand_items=["Rice Basmati", "Coconut", "Coconut Oil", "Banana",
                      "Jaggery", "Papadum", "Desi Ghee"],
        demand_multiplier=2.2,
        prep_days=7,
        tips="Sadya feast ingredients — coconut oil, rice, banana, pappadam — heavy demand.",
    ),
    Festival(
        key="ganesh_chaturthi",
        name="Ganesh Chaturthi",
        name_te="వినాయక చవితి",
        months=[8, 9],
        region="all",
        demand_items=["Coconut", "Jaggery", "Sesame Seeds", "Banana",
                      "Desi Ghee", "Moong Dal"],
        demand_multiplier=3.0,
        prep_days=7,
        tips="Modak / Undrallu ingredients: coconut, jaggery, moong, sesame — stock 3× a week before.",
    ),
    Festival(
        key="navratri",
        name="Navratri / Dussehra",
        name_te="నవరాత్రి / దసరా",
        months=[10],
        region="all",
        demand_items=["Coconut", "Banana", "Desi Ghee", "Sugar",
                      "Milk", "Curd", "Turmeric Powder"],
        demand_multiplier=2.2,
        prep_days=5,
        tips="Golu festival in South India — fruits, coconut, turmeric on high demand.",
    ),
    Festival(
        key="diwali",
        name="Diwali",
        name_te="దీపావళి",
        months=[10, 11],
        region="all",
        demand_items=["Desi Ghee", "Sugar", "Coconut", "Sesame Seeds",
                      "Jaggery", "Desi Ghee", "Snacks & Biscuits",
                      "Oils & Ghee", "Milk"],
        demand_multiplier=4.0,
        prep_days=14,
        tips="Biggest sales event of the year. Start stocking 2 weeks ahead."
             " Sweets, dry fruits, oils, ghee — everything spikes 4×.",
    ),
    Festival(
        key="kartik_purnima",
        name="Kartik Purnima / Deepotsavam",
        name_te="కార్తీక పౌర్ణమి",
        months=[11],
        region="south",
        demand_items=["Coconut Oil", "Coconut", "Banana", "Turmeric Powder"],
        demand_multiplier=1.8,
        prep_days=4,
        tips="Lighting lamps with coconut oil is traditional in Andhra/Telangana.",
    ),
    Festival(
        key="christmas",
        name="Christmas",
        name_te="క్రిస్మస్",
        months=[12],
        region="all",
        demand_items=["Sugar", "Milk", "Desi Ghee", "Snacks & Biscuits", "Beverages"],
        demand_multiplier=1.5,
        prep_days=5,
        tips="Cakes, sweets, and beverages see steady pickup in South India around Dec 25.",
    ),
    Festival(
        key="new_year",
        name="New Year",
        name_te="నూతన సంవత్సరం",
        months=[12, 1],
        region="all",
        demand_items=["Beverages", "Snacks & Biscuits", "Sugar"],
        demand_multiplier=1.4,
        prep_days=3,
        tips="Party snacks, beverages, and sweets spike toward Dec 31 / Jan 1.",
    ),
]

# Seasonal weather patterns for South India
SEASONAL_CONTEXT = {
    1:  {"season": "Winter",          "note": "Cool and dry. High demand for warm beverages, ghee, sesame."},
    2:  {"season": "Late Winter",     "note": "Dry weather. Focus on long-shelf grains and pulses."},
    3:  {"season": "Spring",          "note": "Harvest season. Tamarind, mango, fresh produce spike."},
    4:  {"season": "Summer",          "note": "Peak heat. Buttermilk, coconut water, cold beverages surge."},
    5:  {"season": "Summer",          "note": "Very hot. Stock curd, buttermilk, coconut — daily essentials."},
    6:  {"season": "Pre-Monsoon",     "note": "Stock up before monsoon disrupts supply chains."},
    7:  {"season": "Monsoon",         "note": "Rain disrupts delivery. Keep 2× buffer on all staples."},
    8:  {"season": "Monsoon",         "note": "Supply chains stressed. Prioritize staples over perishables."},
    9:  {"season": "Monsoon end",     "note": "Festive season begins. Start festival stocking now."},
    10: {"season": "Post-Monsoon",    "note": "Festival peak — Navratri, Diwali. Maximum demand period."},
    11: {"season": "Early Winter",    "note": "Festival tail. Clear perishable stock before winter."},
    12: {"season": "Winter",          "note": "Year-end. Balance between clearing stock and festive bump."},
}


def get_upcoming_festivals(days_ahead: int = 30) -> list[dict]:
    """Return festivals falling in the next N days (approximate by month window)."""
    today = datetime.date.today()
    current_month = today.month
    future_month = (today + datetime.timedelta(days=days_ahead)).month

    months_to_check = set()
    m = current_month
    while True:
        months_to_check.add(m)
        if m == future_month:
            break
        m = m % 12 + 1

    upcoming = []
    for fest in FESTIVALS:
        if any(mo in months_to_check for mo in fest.months):
            upcoming.append({
                "key": fest.key,
                "name": fest.name,
                "name_te": fest.name_te,
                "region": fest.region,
                "demand_items": fest.demand_items,
                "demand_multiplier": fest.demand_multiplier,
                "prep_days": fest.prep_days,
                "tips": fest.tips,
            })

    return upcoming


def get_seasonal_context() -> dict:
    month = datetime.date.today().month
    return SEASONAL_CONTEXT.get(month, {"season": "Unknown", "note": ""})


def get_demand_multiplier(product_name: str) -> float:
    """Return highest applicable demand multiplier for a product given upcoming festivals."""
    upcoming = get_upcoming_festivals(days_ahead=21)
    max_mult = 1.0
    name_lower = product_name.lower()
    for fest in upcoming:
        for item in fest["demand_items"]:
            if item.lower() in name_lower or name_lower in item.lower():
                max_mult = max(max_mult, fest["demand_multiplier"])
    return max_mult


def build_seasonal_summary() -> str:
    """Plain-text summary for the LangGraph agent prompt."""
    today = datetime.date.today()
    ctx = get_seasonal_context()
    upcoming = get_upcoming_festivals(days_ahead=30)

    lines = [
        f"Date: {today.isoformat()}",
        f"Season: {ctx['season']} — {ctx['note']}",
        "",
        "Upcoming festivals (next 30 days):",
    ]
    if not upcoming:
        lines.append("  None.")
    else:
        for f in upcoming:
            lines.append(
                f"  • {f['name']} ({f['name_te']}) — {f['demand_multiplier']}× demand spike"
            )
            lines.append(f"    Stock items: {', '.join(f['demand_items'][:6])}")
            lines.append(f"    Tip: {f['tips']}")

    return "\n".join(lines)
