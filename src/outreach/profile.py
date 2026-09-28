"""PopulationProfile: the hand-off from the Data Agent to the Outreach Agent.

The Outreach Agent never sees raw data. It receives this small, fully
computed description of the target population: who they are (filters),
where they live, what they lack compared with India as a whole, and which
channels already reach them. Every number in it comes from SQL.
"""

from dataclasses import asdict, dataclass, field

from src.analysis.database import connect, label_for
from src.analysis.queries import describe_population
from src.data.variables import DEFAULT_UNDERSERVED_INDICATORS, DERIVED_BY_NAME
from src.tools.data_tools import channel_reach, weighted_percentage

PROFILE_DEPRIVATIONS = DEFAULT_UNDERSERVED_INDICATORS + ["any_anemia", "no_mobile_phone", "no_bank_account",
                                                         "never_used_internet"]
ELEVATED_BY = 5.0   # percentage points above national = "elevated" (our threshold)


@dataclass
class PopulationProfile:
    description: str
    filters: list
    states: list                       # lower-case state names
    residence: str = None
    districts: list = field(default_factory=list)
    deprivations: list = field(default_factory=list)   # [{indicator, description, pct, national_pct, n, elevated}]
    reach: list = field(default_factory=list)          # channel reach rows

    def to_dict(self):
        return asdict(self)

    def elevated(self):
        return [d for d in self.deprivations if d["elevated"]]


def states_for(filters):
    """State names implied by the filters (directly via v024, or via district sdist)."""
    states, districts = set(), []
    for f in filters:
        values = f["value"] if isinstance(f["value"], (list, tuple)) else [f["value"]]
        if f["variable"] == "v024" and f.get("op", "=") in ("=", "in"):
            states |= {label_for("v024", v) for v in values}
        if f["variable"] == "sdist" and f.get("op", "=") in ("=", "in"):
            districts += [label_for("sdist", v) for v in values]
            with connect() as connection:
                placeholders = ",".join("?" for _ in values)
                for row in connection.execute(
                        f"SELECT DISTINCT v024 FROM women WHERE sdist IN ({placeholders})", values):
                    states.add(label_for("v024", row["v024"]))
    return sorted(states), districts


def residence_for(filters):
    for f in filters:
        if f["variable"] == "v025" and f.get("op", "=") == "=":
            return label_for("v025", f["value"])
    return None


def build_profile(filters, trace, description=None):
    """Compute the profile, recording every query in the trace."""
    states, districts = states_for(filters)
    deprivations = []
    for name in PROFILE_DEPRIVATIONS:
        target = weighted_percentage(trace, {"indicator": name}, filters)["rows"][0]
        national = weighted_percentage(trace, {"indicator": name})["rows"][0]
        pct, national_pct = target["weighted_pct"], national["weighted_pct"]
        deprivations.append({
            "indicator": name, "description": DERIVED_BY_NAME[name].description,
            "pct": pct, "national_pct": national_pct, "n": target["n_valid"],
            "reliability": target["reliability"],
            "elevated": pct is not None and national_pct is not None and pct >= national_pct + ELEVATED_BY,
        })
    reach = channel_reach(trace, filters)["rows"]
    return PopulationProfile(
        description=description or describe_population(filters),
        filters=filters, states=states, residence=residence_for(filters), districts=districts,
        deprivations=deprivations, reach=reach,
    )
