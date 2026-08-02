"""Conservative SQLite checks/backups for operational databases only."""
from __future__ import annotations
import shutil, sqlite3, time
from contextlib import closing
from pathlib import Path


class DatabaseMaintenanceService:
    def __init__(self, backup_root:str, targets:dict[str,Path]):
        self.backup_root=Path(backup_root)/"database-backups";self.backup_root.mkdir(parents=True,exist_ok=True);self.targets=targets

    def inspect(self,path:Path)->dict:
        if not path.exists():return {"exists":False,"integrity":"missing","size_bytes":0}
        with closing(sqlite3.connect(path)) as conn:
            check=str(conn.execute("PRAGMA quick_check").fetchone()[0]);pages=int(conn.execute("PRAGMA page_count").fetchone()[0]);free=int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        return {"exists":True,"integrity":check,"size_bytes":path.stat().st_size,"page_count":pages,"free_pages":free,"reclaimable_ratio":round(free/max(1,pages),4)}

    def status(self)->dict:return {name:self.inspect(path) for name,path in self.targets.items()}

    def backup(self,name:str)->Path:
        path=self.targets[name];target_dir=self.backup_root/name;target_dir.mkdir(parents=True,exist_ok=True);target=target_dir/f"{int(time.time())}.sqlite"
        with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(target)) as destination:
            source.backup(destination)
        if self.inspect(target)["integrity"]!="ok":target.unlink(missing_ok=True);raise RuntimeError("database backup verification failed")
        backups=sorted(target_dir.glob("*.sqlite"),key=lambda item:item.stat().st_mtime,reverse=True)
        for old in backups[3:]:old.unlink(missing_ok=True)
        return target

    def maintain(self,name:str,allow_vacuum:bool=False)->dict:
        if name not in self.targets:raise ValueError("unknown database")
        path=self.targets[name];before=self.inspect(path)
        if before["integrity"]!="ok":return {"database":name,"status":"needs_recovery","before":before}
        backup=str(self.backup(name))
        with closing(sqlite3.connect(path,timeout=5)) as conn:
            conn.execute("PRAGMA wal_checkpoint(PASSIVE)");conn.execute("PRAGMA optimize")
            if allow_vacuum and before["reclaimable_ratio"]>=.2 and shutil.disk_usage(path.parent).free>max(10_000_000,before["size_bytes"]*2):conn.execute("VACUUM")
            conn.commit()
        return {"database":name,"status":"maintained","backup":backup,"before":before,"after":self.inspect(path)}
