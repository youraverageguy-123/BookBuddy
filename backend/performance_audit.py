"""Evaluate release-build timing and process-tree memory samples against pre-v1 budgets."""
from __future__ import annotations
import argparse, csv, io, json, math, os, subprocess, time
from pathlib import Path

TIME_BUDGETS_MS={"cold_start":3000,"reader_open":500,"resume":400,"page_turn":80,"theme_reflow":150,"selection_toolbar":120,"dictionary_cached":200,"indexed_search":200,"import_5mb":2000,"home_interaction":100,"annotation_save":100}
MEMORY_BUDGETS_MB={"idle":250,"ordinary_book":350,"illustrated_book":600,"main_during_analysis":350,"heavy_worker_soft":1024,"heavy_worker_hard":1536}

def percentile(values:list[float],fraction:float)->float:
    if not values:return 0.0
    ordered=sorted(values); index=max(0,min(len(ordered)-1,math.ceil(len(ordered)*fraction)-1)); return ordered[index]

def process_tree_working_set(pid:int)->float:
    if os.name!="nt":
        total=0
        descendants={pid}
        changed=True
        while changed:
            changed=False
            for entry in Path("/proc").iterdir():
                if not entry.name.isdigit():continue
                try:
                    fields=(entry/"stat").read_text(encoding="utf-8").split(); child=int(fields[0]); parent=int(fields[3])
                    if parent in descendants and child not in descendants:descendants.add(child);changed=True
                except (OSError,ValueError,IndexError):pass
        for child in descendants:
            try:
                status=(Path("/proc")/str(child)/"status").read_text(encoding="utf-8")
                total+=int(next(line.split()[1] for line in status.splitlines() if line.startswith("VmRSS:")))*1024
            except (OSError,StopIteration,ValueError):pass
        return total/(1024*1024)
    command=f"$root={int(pid)};$all=Get-CimInstance Win32_Process;$ids=@($root);do{{$before=$ids.Count;$ids+=@($all|Where-Object{{$ids -contains $_.ParentProcessId}}|ForEach-Object{{$_.ProcessId}});$ids=@($ids|Select-Object -Unique)}}while($ids.Count -gt $before);Get-Process -Id $ids -ErrorAction SilentlyContinue|ForEach-Object{{$_.WorkingSet64}}"
    output=subprocess.check_output(["powershell","-NoProfile","-Command",command],text=True,timeout=15)
    return sum(float(line) for line in output.splitlines() if line.strip())/(1024*1024)

def evaluate(payload:dict)->dict:
    operations={}
    for name,budget in TIME_BUDGETS_MS.items():
        values=[float(value) for value in payload.get("timings_ms",{}).get(name,[])]
        p95=percentile(values,.95); operations[name]={"samples":len(values),"median_ms":round(percentile(values,.5),2),"p95_ms":round(p95,2),"budget_ms":budget,"passed":len(values)>=10 and p95<budget}
    memory={}
    for name,budget in MEMORY_BUDGETS_MB.items():
        values=[float(value) for value in payload.get("memory_mb",{}).get(name,[])]
        peak=max(values,default=0); memory[name]={"samples":len(values),"peak_mb":round(peak,2),"budget_mb":budget,"passed":bool(values) and peak<budget}
    return {"schema_version":"bookbuddy_performance_audit_v1","generated_at":time.time(),"measurement_contract":payload.get("measurement_contract",{}),"timings":operations,"memory":memory,"passed":all(item["passed"] for item in operations.values()) and all(item["passed"] for item in memory.values())}

def main()->int:
    parser=argparse.ArgumentParser();parser.add_argument("--samples",required=True);parser.add_argument("--output",default="audit-results/performance-budget.json");args=parser.parse_args()
    report=evaluate(json.loads(Path(args.samples).read_text(encoding="utf-8")));target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps({"output":str(target),"passed":report["passed"]}));return 0 if report["passed"] else 1
if __name__=="__main__":raise SystemExit(main())
