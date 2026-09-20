#!/usr/bin/env python3
"""Minimal newline-delimited stdio MCP server for Nereus tools."""
import json, os, sys
from nereus_agent_tools import NereusToolkit, TOOL_SCHEMAS, dispatch

def send(value):
    sys.stdout.write(json.dumps(value, ensure_ascii=False)+"\n"); sys.stdout.flush()

def tool_result(value):
    value=dict(value); image=value.pop("_mcp_image",None)
    content=[{"type":"text","text":json.dumps(value,ensure_ascii=False)}]
    if image: content.append({"type":"image",**image})
    return {"content":content,"isError":not value.get("ok",False)}

def main():
    toolkit=NereusToolkit(base_url=os.getenv("NEREUS_BASE_URL","https://nereus.ooirsn.uw.edu"),query_dir=os.getenv("NEREUS_QUERY_DIR"),cache_dir=os.getenv("NEREUS_CACHE_DIR"),snapshot_dir=os.getenv("NEREUS_SNAPSHOT_DIR"))
    for line in sys.stdin:
        try:
            req=json.loads(line); method=req.get("method"); req_id=req.get("id")
            if method=="initialize": result={"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"rcn-agent-nereus","version":"1.0.0"}}
            elif method=="tools/list": result={"tools":TOOL_SCHEMAS}
            elif method=="tools/call":
                params=req.get("params",{}); result=tool_result(dispatch(toolkit,params.get("name",""),params.get("arguments",{})))
            elif method and method.startswith("notifications/"): continue
            else: send({"jsonrpc":"2.0","id":req_id,"error":{"code":-32601,"message":f"Method not found: {method}"}}); continue
            send({"jsonrpc":"2.0","id":req_id,"result":result})
        except Exception as exc: send({"jsonrpc":"2.0","id":None,"error":{"code":-32603,"message":str(exc)}})

if __name__=="__main__": main()
