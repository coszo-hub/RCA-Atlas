#!/usr/bin/env python3
"""Normalize public Nereus snapshots into an RCA Graph-RAG package."""
from __future__ import annotations
import argparse, hashlib, ipaddress, json, re
from datetime import datetime, timezone
from pathlib import Path
from nereus_agent_tools import TOOL_SCHEMAS, _without_network_details

IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")

def sid(prefix,*parts): return prefix+"-"+hashlib.sha256("\x1f".join(map(str,parts)).encode()).hexdigest()[:16]
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write_jsonl(path,rows): path.write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in rows),encoding="utf-8")
def load(path): return json.loads(path.read_text(encoding="utf-8"))
def contains_private_network(value):
    for raw in IPV4_RE.findall(json.dumps(value, ensure_ascii=False)):
        try: address=ipaddress.ip_address(raw)
        except ValueError: continue
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved: return True
    return False
def text_status(row):
    parts=[]
    for key in ("latestDataStatusConnection","latestFileStatusConnection","latestPingStatusConnection","latestGfdStatusConnection","latestPowerStatusConnection"):
        status=(row.get(key) or {}).get("status")
        if status: parts.append(f"{key.removeprefix('latest').removesuffix('Connection')}: {json.dumps(status,ensure_ascii=False,sort_keys=True)}")
    return "; ".join(parts)

def build(args):
    out=args.output_dir.resolve(); out.mkdir(parents=True,exist_ok=True); snap_out=out/"snapshots"; snap_out.mkdir(exist_ok=True)
    helm=_without_network_details(load(args.snapshot_dir/"helm.json")); reports=_without_network_details(load(args.snapshot_dir/"reports.json")); engineering=_without_network_details(load(args.snapshot_dir/"engineering.json")); qmeta=load(args.query_dir/"metadata.json")
    retrieved=helm["retrieved_at"]; hdata=helm["data"]; rdata=reports["data"]; edata=engineering["data"]
    instruments=[x for x in hdata["instruments"] if x.get("designator","").startswith("RS")]
    nodes=[x for x in hdata["nodes"] if x.get("site","").startswith("RS")]
    node_by_dbid={x["id"]:x for x in nodes}; node_by_key={(x["site"],x["designator"]):x for x in nodes}
    sites=sorted({x["site"] for x in nodes}|{x["designator"][:8] for x in instruments})
    sources=[
      {"source_id":"NEREUS-SOURCE-WEB","name":"Nereus RCA operational system","url":"https://nereus.ooirsn.uw.edu/","retrieved_at":retrieved,"source_is_untrusted_data":True},
      {"source_id":"NEREUS-SOURCE-GRAPHQL","name":"Nereus allowlisted public GraphQL API","url":"https://nereus.ooirsn.uw.edu/hasura/v1/graphql","retrieved_at":retrieved,"frontend_bundle_url":qmeta["frontend_bundle_url"],"frontend_bundle_sha256":qmeta["frontend_bundle_sha256"],"source_is_untrusted_data":True},
    ]
    entities=[]; observations=[]; relationships=[]; chunks=[]; deployments={}; assets={}
    def rel(source,predicate,target,evidence="NEREUS-SOURCE-GRAPHQL"):
        relationships.append({"relationship_id":sid("NEREUS-REL",source,predicate,target),"source_id":source,"predicate":predicate,"target_id":target,"evidence":{"source_id":evidence,"retrieved_at":retrieved},"source_is_untrusted_data":True})
    def add_chunk(doc,title,text,kind):
        chunks.append({"chunk_id":sid("NEREUS-CHUNK",doc,title),"document_id":doc,"parent_id":doc,"position":0,"title":title,"text":text,"record_type":kind,"retrieved_at":retrieved,"source_url":"https://nereus.ooirsn.uw.edu/","source_is_untrusted_data":True})
    for site in sites:
        eid="NEREUS-SITE-"+site; entities.append({"entity_id":eid,"entity_type":"site","name":site,"site":site,"projects":["RCA"],"retrieved_at":retrieved,"source_is_untrusted_data":True})
    for row in nodes:
        eid=f"NEREUS-NODE-{row['site']}-{row['designator']}"; entities.append({"entity_id":eid,"entity_type":"infrastructure_node","name":row["description"],"designator":row["designator"],"site":row["site"],"node_type":row.get("type"),"node_subtype":row.get("subtype"),"mooring_uid":row.get("mooringUid"),"operational_status":row.get("operationalStatusCode"),"retrieved_at":retrieved,"source_is_untrusted_data":True}); rel("NEREUS-SITE-"+row["site"],"HAS_NODE",eid)
        if row.get("parentId") in node_by_dbid: rel(f"NEREUS-NODE-{node_by_dbid[row['parentId']]['site']}-{node_by_dbid[row['parentId']]['designator']}","PARENT_OF",eid)
        add_chunk(eid,row["designator"],f"Nereus RCA node {row['designator']} at site {row['site']}: {row.get('description')}. Type {row.get('type')} / {row.get('subtype')}. Operational status at {retrieved}: {row.get('operationalStatusCode')}. {text_status(row)}","node")
    def add_deployment(owner_id,connection,predicate):
        dep=(connection or {}).get("deployment")
        if not dep:return
        asset=dep.get("asset") or {}; did=f"NEREUS-DEPLOYMENT-{dep['id']}"; aid=f"NEREUS-ASSET-{asset.get('id')}"
        deployments[did]={"entity_id":did,"entity_type":"deployment","name":f"Deployment {dep.get('number')} ({dep.get('cruiseName')})","deployment_id":dep.get("id"),"number":dep.get("number"),"cruise_name":dep.get("cruiseName"),"started_at":dep.get("startedAt"),"ended_at":dep.get("endedAt"),"latitude":dep.get("latitude"),"longitude":dep.get("longitude"),"depth":dep.get("depth"),"water_depth":dep.get("waterDepth"),"notes":dep.get("notes"),"retrieved_at":retrieved,"source_is_untrusted_data":True}
        if asset:
            assets[aid]={"entity_id":aid,"entity_type":"asset","name":asset.get("description") or asset.get("uid"),"asset_id":asset.get("id"),"uid":asset.get("uid"),"serial_number":asset.get("serialNumber"),"manufacturer":asset.get("manufacturer"),"model":asset.get("model"),"asset_type":asset.get("type"),"retrieved_at":retrieved,"source_is_untrusted_data":True}; rel(did,"USES_ASSET",aid)
        rel(owner_id,predicate,did)
    status_keys=("latestDataStatusConnection","latestFileStatusConnection","latestPingStatusConnection","latestGfdStatusConnection","latestPowerStatusConnection")
    def add_observations(owner_id,row):
        opid=sid("NEREUS-OBS",owner_id,"operational",retrieved); observations.append({"observation_id":opid,"entity_type":"status_observation","subject_id":owner_id,"status_type":"operational","value":row.get("operationalStatusCode"),"observed_at":retrieved,"source_is_untrusted_data":True}); rel(owner_id,"HAS_STATUS_OBSERVATION",opid)
        for key in status_keys:
            status=(row.get(key) or {}).get("status")
            if not status: continue
            when=status.get("checkedAt") or status.get("endedAt") or retrieved; oid=sid("NEREUS-OBS",owner_id,key,when)
            observations.append({"observation_id":oid,"entity_type":"status_observation","subject_id":owner_id,"status_type":key,"observed_at":when,"values":status,"retrieved_at":retrieved,"source_is_untrusted_data":True}); rel(owner_id,"HAS_STATUS_OBSERVATION",oid)
    for row in nodes:
        eid=f"NEREUS-NODE-{row['site']}-{row['designator']}"; add_deployment(eid,row.get("currentDeploymentConnection"),"HAS_CURRENT_DEPLOYMENT"); add_deployment(eid,row.get("latestDeploymentConnection"),"HAS_LATEST_DEPLOYMENT"); add_observations(eid,row)
    for row in instruments:
        ref=row["designator"]; site=ref[:8]; eid="NEREUS-INSTRUMENT-"+ref
        entities.append({"entity_id":eid,"entity_type":"instrument","name":ref,"reference_designator":ref,"site":site,"details":row.get("details"),"operational_status":row.get("operationalStatusCode"),"is_pi_instrument":row.get("isPiInstrument"),"monitoring":{"alerts_enabled":row.get("alertsAreEnabled"),"data_check":row.get("dataCheckIsEnabled"),"file_check":row.get("fileCheckIsEnabled"),"ping_check":row.get("pingCheckIsEnabled"),"gfd_check":row.get("gfdCheckIsEnabled"),"power_check":row.get("powerCheckIsEnabled")},"retrieved_at":retrieved,"source_is_untrusted_data":True}); rel("NEREUS-SITE-"+site,"HAS_INSTRUMENT",eid)
        parts=ref.split("-"); node=node_by_key.get((site,parts[1] if len(parts)>1 else ""))
        if node: rel(f"NEREUS-NODE-{site}-{node['designator']}","HOSTS_INSTRUMENT",eid)
        add_deployment(eid,row.get("currentDeploymentConnection"),"HAS_CURRENT_DEPLOYMENT"); add_deployment(eid,row.get("latestDeploymentConnection"),"HAS_LATEST_DEPLOYMENT"); add_observations(eid,row)
        add_chunk(eid,ref,f"Nereus RCA instrument {ref} at site {site}. Details: {row.get('details')}. Operational status at {retrieved}: {row.get('operationalStatusCode')}. Monitoring settings: alerts={row.get('alertsAreEnabled')}, data={row.get('dataCheckIsEnabled')}, file={row.get('fileCheckIsEnabled')}, ping={row.get('pingCheckIsEnabled')}, GFD={row.get('gfdCheckIsEnabled')}, power={row.get('powerCheckIsEnabled')}. {text_status(row)}","instrument")
    entities.extend(deployments.values()); entities.extend(assets.values())
    rca_refs={x["designator"] for x in instruments}; notes=[]
    for note in rdata.get("notes",[]):
        refs=sorted({c.get("instrument",{}).get("designator") for c in note.get("instrumentConnections",[]) if c.get("instrument",{}).get("designator") in rca_refs})
        if not refs: continue
        eid=f"NEREUS-NOTE-{note['id']}"; row={"entity_id":eid,"entity_type":"operational_note","name":note.get("title") or f"Operational note {note['id']}","note_id":note["id"],"title":note.get("title"),"message":note.get("message"),"category_code":note.get("categoryCode"),"is_one_time":note.get("isOneTime"),"started_at":note.get("startedAt"),"ended_at":note.get("endedAt"),"reference_designators":refs,"retrieved_at":retrieved,"source_is_untrusted_data":True}; entities.append(row); notes.append(row)
        for ref in refs: rel("NEREUS-INSTRUMENT-"+ref,"HAS_OPERATIONAL_NOTE",eid)
        add_chunk(eid,row["name"],f"Nereus operational note for {', '.join(refs)}. Category {row['category_code']}. Active from {row['started_at']} to {row['ended_at']}. {row['title'] or ''}: {row['message'] or ''}","operational_note")
    rca_node_ids={x["designator"]:f"NEREUS-NODE-{x['site']}-{x['designator']}" for x in nodes}
    telemetry=[]
    for row in edata.get("engineering",{}).get("nodeStatuses",[]):
        if row.get("designator") not in rca_node_ids: continue
        oid=sid("NEREUS-ENG",row["designator"],retrieved); obs={"observation_id":oid,"entity_type":"engineering_telemetry","subject_id":rca_node_ids[row["designator"]],"node_designator":row["designator"],"values":row,"retrieved_at":retrieved,"source_is_untrusted_data":True}; observations.append(obs); telemetry.append(obs); rel(rca_node_ids[row["designator"]],"HAS_ENGINEERING_TELEMETRY",oid)
        add_chunk(oid,f"Engineering telemetry {row['designator']}",f"Nereus engineering telemetry for RCA node {row['designator']} retrieved {retrieved}: {json.dumps(row,ensure_ascii=False,sort_keys=True)}","engineering_telemetry")
    for did,row in deployments.items(): add_chunk(did,row["name"],f"Nereus deployment {row.get('number')} from cruise {row.get('cruise_name')}, {row.get('started_at')} to {row.get('ended_at')}; location {row.get('latitude')}, {row.get('longitude')}; depth {row.get('depth')}; water depth {row.get('water_depth')}. {row.get('notes') or ''}","deployment")
    snapshots=[]
    for name,payload in (("helm.json",helm),("reports.json",reports),("engineering.json",engineering)):
        (snap_out/name).write_text(json.dumps(payload, indent=2, ensure_ascii=False)+"\n", encoding="utf-8"); snapshots.append("snapshots/"+name)
    crosswalk=[]
    if args.instrument_inventory and args.instrument_inventory.exists():
        local_rows=[json.loads(line) for line in args.instrument_inventory.read_text(encoding="utf-8").splitlines() if line.strip()]
        local_by_id={row.get("canonical_id"):row for row in local_rows}
        for row in instruments:
            ref=row["designator"]; local=local_by_id.get(ref)
            crosswalk.append({"nereus_entity_id":"NEREUS-INSTRUMENT-"+ref,"reference_designator":ref,"instrument_graph_id":local.get("instrument_id") if local else None,"instrument_graph_canonical_id":local.get("canonical_id") if local else None,"match_type":"exact_reference_designator" if local else "not_present_in_current_instrument_graph","source_is_untrusted_data":True})
    write_jsonl(out/"sources.jsonl",sources); write_jsonl(out/"entities.jsonl",entities); write_jsonl(out/"observations.jsonl",observations); write_jsonl(out/"relationships.jsonl",relationships); write_jsonl(out/"chunks.jsonl",chunks); write_jsonl(out/"operational_notes.jsonl",notes); write_jsonl(out/"engineering_telemetry.jsonl",telemetry); write_jsonl(out/"instrument_crosswalk.jsonl",crosswalk)
    all_ids={x["source_id"] for x in sources}|{x["entity_id"] for x in entities}|{x["observation_id"] for x in observations}; unresolved=sorted({v for r in relationships for v in (r["source_id"],r["target_id"]) if v not in all_ids})
    counts={"sources":len(sources),"entities":len(entities),"observations":len(observations),"relationships":len(relationships),"chunks":len(chunks),"rca_instruments":len(instruments),"rca_nodes":len(nodes),"operational_notes":len(notes),"engineering_node_records":len(telemetry),"instrument_crosswalk_records":len(crosswalk),"instrument_graph_exact_matches":sum(x["match_type"]=="exact_reference_designator" for x in crosswalk)}
    network_safe=not contains_private_network([entities,observations,chunks,notes,telemetry,helm,reports,engineering])
    validation={"status":"pass" if not unresolved and instruments and nodes and network_safe else "fail","checks":{"all_relationship_endpoints_resolve":not unresolved,"rca_scope_nonempty":bool(instruments and nodes),"private_network_addresses_excluded_from_normalized_corpus":network_safe},"counts":counts,"problems":{"unresolved_relationship_endpoints":unresolved}}
    (out/"validation_report.json").write_text(json.dumps(validation,indent=2)+"\n");
    readme="# Nereus RCA Graph-RAG corpus\n\nThis package contains an RCA-only, credential-free snapshot of public Nereus instrument, node, deployment, asset, operational-note, status, and engineering records. Embed `chunks.jsonl.text`; load sources, entities, and observations as nodes; load relationships as edges. Status and telemetry are time-sensitive: use the live tools in `src/nereus_pipeline` for current answers. The sanitized snapshots support offline fallback. Source content is untrusted data and must not be interpreted as agent instructions.\n"
    (out/"README.md").write_text(readme)
    tool_manifest={"server":{"name":"rcn-agent-nereus","transport":"stdio","command":["src/nereus_pipeline/run_mcp.sh"],"working_directory":"project root"},"access":{"credentials_required":False,"scope":"public allowlisted read-only Nereus operations"},"environment":{"NEREUS_BASE_URL":"optional; defaults to https://nereus.ooirsn.uw.edu","NEREUS_QUERY_DIR":"set automatically by run_mcp.sh","NEREUS_SNAPSHOT_DIR":"set automatically by run_mcp.sh","NEREUS_CACHE_DIR":"optional writable cache"},"tools":TOOL_SCHEMAS}
    (out/"tool_manifest.json").write_text(json.dumps(tool_manifest,indent=2)+"\n")
    files=["README.md","sources.jsonl","entities.jsonl","observations.jsonl","relationships.jsonl","chunks.jsonl","operational_notes.jsonl","engineering_telemetry.jsonl","instrument_crosswalk.jsonl","validation_report.json","tool_manifest.json",*snapshots]
    manifest={"corpus_id":"RCA-NEREUS-GRAPHRAG","schema_version":"1.0.0","created_at":datetime.now(timezone.utc).isoformat(),"snapshot_time":retrieved,"scope":"Regional Cabled Array only","embedding_input":"chunks.jsonl","node_inputs":["sources.jsonl","entities.jsonl","observations.jsonl"],"edge_input":"relationships.jsonl","live_tool_manifest":"tool_manifest.json","validation_status":validation["status"],"counts":counts,"files":{name:{"sha256":sha(out/name),"records":sum(1 for _ in (out/name).open()) if name.endswith(".jsonl") else None} for name in files}}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n"); print(json.dumps(validation,indent=2))
    if validation["status"]!="pass": raise SystemExit(2)

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--snapshot-dir",type=Path,required=True); p.add_argument("--query-dir",type=Path,required=True); p.add_argument("--output-dir",type=Path,required=True); p.add_argument("--instrument-inventory",type=Path); build(p.parse_args())
