#!/usr/bin/env python3
"""Capture sanitized public Nereus responses for reproducible corpus builds."""
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
from nereus_agent_tools import NereusToolkit, _without_network_details

def main():
    p=argparse.ArgumentParser(); p.add_argument("--output-dir",type=Path,required=True); p.add_argument("--cutoff",default="2025-01-01T00:00:00Z"); args=p.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    toolkit=NereusToolkit(cache_ttl_seconds=0)
    operations=[("HelmQuery",{},"helm.json"),("ReportsPageQuery",{"cutoff":args.cutoff},"reports.json"),("EngineeringQuery",{},"engineering.json")]
    retrieved=datetime.now(timezone.utc).isoformat()
    for operation,variables,name in operations:
        result=toolkit.execute(operation,variables,force_refresh=True)
        if not result.get("ok"): raise SystemExit(json.dumps(result,indent=2))
        payload={"operation":operation,"variables":variables,"retrieved_at":retrieved,"source_url":result["source_url"],"source_is_untrusted_data":True,"data":_without_network_details(result["data"])}
        (args.output_dir/name).write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"ok":True,"retrieved_at":retrieved,"files":[x[2] for x in operations]},indent=2))

if __name__=="__main__": main()
