#!/usr/bin/env python3
"""Validate and make a deliberately non-authorizing AYN Thor profile plan."""
from __future__ import annotations
import argparse, json, posixpath, sys
from pathlib import Path
ROOT=Path(__file__).parent; DEFAULT_PROFILE=ROOT/"profiles"/"ayn-thor-v1.json"
REQUIRED_TOP={"schema_version","profile","profile_version","rom_root","emulators","acceptance"}

def load_profile(path: Path=DEFAULT_PROFILE)->dict:
    data=json.loads(path.read_text()); missing=REQUIRED_TOP-data.keys()
    if missing: raise ValueError("profile missing fields: "+", ".join(sorted(missing)))
    if not isinstance(data["schema_version"],int) or data["schema_version"]!=1: raise ValueError("schema_version must be integer 1")
    for key in ("profile","profile_version"):
        if not isinstance(data[key],str) or not data[key].strip(): raise ValueError(f"{key} must be a non-empty string")
    if data["rom_root"]!="${ROM_ROOT}": raise ValueError("rom_root must be ${ROM_ROOT}")
    if not isinstance(data["emulators"],dict) or not data["emulators"]: raise ValueError("emulators must be a non-empty object")
    if not isinstance(data["acceptance"],list) or not all(isinstance(x,str) for x in data["acceptance"]): raise ValueError("acceptance must be a string list")
    for name,item in data["emulators"].items():
        if not isinstance(item,dict) or not isinstance(item.get("platforms"),list) or not isinstance(item.get("manual"),list): raise ValueError(f"{name}: platforms/manual must be lists")
        for key in ("rom_paths","bios_path"):
            paths=item.get(key,[]); paths=[paths] if isinstance(paths,str) else paths
            for candidate in paths:
                if not isinstance(candidate,str) or (candidate!="${ROM_ROOT}" and not candidate.startswith("${ROM_ROOT}/")): raise ValueError(f"{name}: {key} must use ROM_ROOT")
                suffix=candidate[len("${ROM_ROOT}"):]
                if ".." in suffix.split("/"): raise ValueError(f"{name}: {key} traversal is not allowed")
    return data

def resolve_under_root(root:str,candidate:str)->str:
    if not isinstance(root,str) or not root.startswith("/") or root=="/": raise ValueError("ROM root must be a non-root absolute POSIX path")
    if candidate!="${ROM_ROOT}" and not candidate.startswith("${ROM_ROOT}/"): raise ValueError("profile path does not use ROM_ROOT")
    resolved=posixpath.normpath(root.rstrip("/")+candidate[len("${ROM_ROOT}"):])
    if posixpath.commonpath((root.rstrip("/"),resolved))!=root.rstrip("/"): raise ValueError("resolved path escapes selected ROM root")
    return resolved

def plan(profile:dict,serial:str|None=None,capabilities:dict|None=None,rom_root:str|None=None)->dict:
    caps=capabilities or {}; missing=[x for x in profile.get("required_capabilities",[]) if not caps.get(x,{}).get("ok",False)]
    resolved={name:[resolve_under_root(rom_root,p) for p in item.get("rom_paths",[])] for name,item in profile["emulators"].items()} if rom_root else {}
    return {"schema_version":1,"profile":profile["profile"],"profile_version":profile["profile_version"],"serial":serial,"selected_rom_root":rom_root,"resolved_rom_paths":resolved,"plan_ready":bool(serial and rom_root and not missing),"authorization":"non_authorizing","missing_capabilities":missing,"auto_deployable":profile.get("auto_deployable",{}),"manual_tasks":{n:i["manual"] for n,i in profile["emulators"].items()},"guardrails":["this plan never authorizes deployment","explicit serial + live fingerprint required","SAF-selected/device-discovered root + storage/free-space preflight required","discover/approve APK package/version/signature","hash every push and never suppress install errors","never log keys, firmware, BIOS, or credentials"]}

def main(argv=None)->int:
    p=argparse.ArgumentParser(); p.add_argument("command",choices=("validate","plan")); p.add_argument("--profile",type=Path,default=DEFAULT_PROFILE); p.add_argument("--serial"); p.add_argument("--rom-root"); p.add_argument("--capabilities",type=Path); p.add_argument("--output",type=Path); a=p.parse_args(argv)
    try:
        profile=load_profile(a.profile); result={"valid":True,"emulator_count":len(profile["emulators"])} if a.command=="validate" else plan(profile,a.serial,json.loads(a.capabilities.read_text()) if a.capabilities else {},a.rom_root)
    except (OSError,ValueError,TypeError,json.JSONDecodeError) as exc: print(f"profile error: {exc}",file=sys.stderr); return 2
    text=json.dumps(result,indent=2)+"\n"; a.output and a.output.write_text(text); print(text,end=""); return 0
if __name__=="__main__": raise SystemExit(main())
