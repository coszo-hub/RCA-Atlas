"""Sensor status: Nereus when the reference designator matches, else planned (new COSZO), else unknown."""
from __future__ import annotations

PLANNED_ROLES = {"new_sensor_suite", "Oregon_Shelf_suite"}
STATUS_GROUP = {
    "OPERATIONAL": "operating", "PARTIALLY_FUNCTIONAL": "operating",
    "NOT_DEPLOYED": "offline", "RETIRED": "offline", "SUPERSEDED": "offline",
    "RECOVERED": "offline", "UNCABLED": "offline",
    "PLANNED": "planned", "UNKNOWN": "unknown",
}


def load_status_index(entities: list[dict], crosswalk: list[dict]) -> dict[str, dict]:
    by_refdes = {e["reference_designator"]: e for e in entities if e.get("entity_type") == "instrument"}
    index = {}
    for row in crosswalk:
        if row.get("match_type") != "exact_reference_designator" or not row.get("instrument_graph_id"):
            continue
        ent = by_refdes.get(row["reference_designator"])
        if ent:
            index[row["instrument_graph_id"]] = {"status": ent["operational_status"],
                                                 "refdes": row["reference_designator"],
                                                 "asOf": ent.get("retrieved_at")}
    return index


def resolve(record: dict, index: dict[str, dict]) -> dict:
    hit = index.get(record["instrumentId"])
    if hit:
        return {"status": hit["status"], "statusSource": "Nereus snapshot", "statusAsOf": hit["asOf"]}
    if record.get("coszoRole") in PLANNED_ROLES:
        return {"status": "PLANNED", "statusSource": "Inventory: new COSZO sensor", "statusAsOf": None}
    return {"status": "UNKNOWN", "statusSource": None, "statusAsOf": None}
