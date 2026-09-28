"""The curated outreach knowledge base and a transparent relevance rubric.

Facts about organizations come ONLY from documents/outreach/organizations.json,
where each fact carries the URL it was taken from. The rubric below is our
own reasoning, so everything it produces is labelled INFERENCE.

Rubric (points):
    geography  2 = works in the target state; 1 = national program;
               0 = named states don't include the target (kept, with a caveat)
    need       +1 for each of the org's related indicators that is elevated
               (>= 5 points above national) in the target population
    channel    +1 for each of the org's channels that already reaches >= 25%
               of the target population, according to the dataset
"""

from src.rag.documents import load_outreach_kb

# Which dataset reach indicator measures each channel type (our mapping).
CHANNEL_TO_REACH = {
    "television": "watches_tv",
    "radio": "listens_radio",
    "mobile phone (voice / IVR)": "owns_mobile_phone",
    "community health workers": "met_frontline_worker",
    "Anganwadi centres": "met_frontline_worker",
    "door-to-door": "met_frontline_worker",
    "bank accounts": "has_bank_account",
    "direct benefit transfer": "has_bank_account",
}
CHANNEL_REACH_THRESHOLD = 25.0


def organizations():
    kb = load_outreach_kb()
    return kb["organizations"], kb["accessed"]


def assess(org, profile, accessed):
    """Score one organization for one population. Returns None if it is
    clearly out of scope (a state program for a different state)."""
    geography = org["geography"]
    target_states = set(profile.states)
    caveats = []
    if geography["scope"] == "national":
        geo_points, geo_text = 1, "national program/organization (India-wide)"
        if geography.get("detail"):
            caveats.append(geography["detail"])
    elif target_states and target_states & set(geography["states"]):
        geo_points, geo_text = 2, f"works in {', '.join(sorted(target_states & set(geography['states'])))}"
    elif geography["scope"] == "state":
        return None  # a state program elsewhere cannot reach this population
    else:
        geo_points, geo_text = 0, f"named states: {', '.join(geography['states'])}"
        caveats.append(geography.get("detail") or "Its named states do not include the target state.")

    by_indicator = {d["indicator"]: d for d in profile.deprivations}
    need_matches = [by_indicator[i] for i in org.get("related_indicators", [])
                    if i in by_indicator and by_indicator[i]["elevated"]]

    reach_by_name = {r["indicator"]: r for r in profile.reach}
    channel_matches, counted = [], set()
    for channel in org.get("channels", []):
        indicator = CHANNEL_TO_REACH.get(channel)
        row = reach_by_name.get(indicator)
        if indicator in counted:
            continue  # two channels measured by the same indicator count once
        if row and row["weighted_pct"] is not None and row["weighted_pct"] >= CHANNEL_REACH_THRESHOLD:
            channel_matches.append({"channel": channel, **row})
            counted.add(indicator)

    if "secondary" in org.get("source_type", ""):
        caveats.append(f"Source is {org['source_type']}.")
    if org.get("unverified_note"):
        caveats.append(org["unverified_note"])

    return {
        "id": org["id"], "name": org["name"], "type": org["type"], "origin": "curated knowledge base",
        "facts": [{"text": f["text"], "source_url": f["source_url"], "accessed": accessed} for f in org["facts"]],
        "geography": geo_text,
        "score": {"geography": geo_points, "need": len(need_matches), "channel": len(channel_matches),
                  "total": geo_points + len(need_matches) + len(channel_matches)},
        "need_matches": need_matches,
        "channel_matches": channel_matches,
        "inference": inference_text(org, profile, geo_text, need_matches, channel_matches),
        "caveats": caveats,
    }


def inference_text(org, profile, geo_text, need_matches, channel_matches):
    reasons = [f"geography: {geo_text}"]
    for n in need_matches:
        reasons.append(f"its stated work relates to '{n['description'].lower()}', which is {n['pct']}% "
                       f"in this population vs {n['national_pct']}% nationally")
    for c in channel_matches:
        reasons.append(f"it uses {c['channel']}, and {c['weighted_pct']}% of this population "
                       f"'{c['description'].lower()}' (n={c['n_valid']:,})")
    return (f"{org['name']} may be a potentially relevant outreach partner for {profile.description} "
            f"because " + "; ".join(reasons) + ". This is a project inference, not a claim by the organization.")


def rank_organizations(profile):
    orgs, accessed = organizations()
    assessed = [a for a in (assess(o, profile, accessed) for o in orgs) if a is not None]
    return sorted(assessed, key=lambda a: (-a["score"]["total"], a["name"]))


def search_knowledge_base(query, state=None):
    """Plain keyword/geography search over the knowledge base (used as an LLM tool)."""
    orgs, accessed = organizations()
    words = [w for w in query.lower().split() if len(w) > 2]
    hits = []
    for org in orgs:
        text = (org["name"] + " " + " ".join(f["text"] for f in org["facts"]) + " " + " ".join(org["channels"])).lower()
        in_state = (org["geography"]["scope"] == "national" or not state
                    or state.lower() in org["geography"]["states"])
        if in_state and (not words or any(w in text for w in words)):
            hits.append({**org, "accessed": accessed})
    return hits
