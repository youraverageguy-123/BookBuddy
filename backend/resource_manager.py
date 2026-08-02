"""Ownership and bounded cleanup for rebuildable BookBuddy resources."""
from __future__ import annotations
import hashlib,json,os,time
from io import BytesIO
from pathlib import Path

CACHE_LIMITS={"images":256*1024*1024,"covers":128*1024*1024,"dictionary":128*1024*1024,"web":256*1024*1024,"search":512*1024*1024}


class ResourceManager:
    def __init__(self,root:str):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        for name in CACHE_LIMITS:(self.root/name).mkdir(parents=True,exist_ok=True)
        self.cover_manifest=self.root/"covers"/"manifest.json"

    def _manifest(self)->dict:
        try:return json.loads(self.cover_manifest.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError):return {"schema_version":1,"sessions":{}}

    def _save_manifest(self,value:dict)->None:
        temp=self.cover_manifest.with_suffix(".tmp");temp.write_text(json.dumps(value,sort_keys=True),encoding="utf-8");os.replace(temp,self.cover_manifest)

    @staticmethod
    def _safe_svg(content:bytes)->bytes:
        import xml.etree.ElementTree as ET
        root=ET.fromstring(content)
        for parent in root.iter():
            for child in list(parent):
                if child.tag.lower().endswith("script"):parent.remove(child)
            for key in list(parent.attrib):
                value=parent.attrib[key].strip().lower()
                if key.lower().startswith("on") or value.startswith(("javascript:","http:","https:","file:")):del parent.attrib[key]
        return ET.tostring(root,encoding="utf-8",xml_declaration=True)

    def store_cover(self,session_key:str,content:bytes,extension:str)->Path:
        extension=extension.lower()
        if extension==".svg":content=self._safe_svg(content)
        digest=hashlib.sha256(content).hexdigest();directory=self.root/"covers";target=directory/f"{digest}{extension}"
        if not target.exists():target.write_bytes(content)
        preferred=target;variants={}
        if extension in {".jpg",".jpeg",".png",".webp"}:
            try:
                from PIL import Image
                with Image.open(BytesIO(content)) as image:
                    for size in (160,320,640):
                        resized=image.copy();resized.thumbnail((size,int(size*1.5)));variant=directory/f"{digest}-{size}.webp";resized.convert("RGB").save(variant,"WEBP",quality=88,method=4);variants[str(size)]=variant.name
                    preferred=directory/variants["640"]
            except Exception:pass
        manifest=self._manifest();manifest.setdefault("sessions",{})[session_key]={"path":preferred.name,"variants":variants,"hash":digest,"updated_at":time.time()};self._save_manifest(manifest);self.prune("covers");return preferred

    def cover(self,session_key:str,size:int=640)->Path|None:
        item=self._manifest().get("sessions",{}).get(session_key)
        if not item:return None
        variants=item.get("variants",{}) if isinstance(item.get("variants",{}),dict) else {}
        path=self.root/"covers"/Path(str(variants.get(str(size),item.get("path","")))).name
        if path.is_file():os.utime(path,None);return path
        return None

    def cover_hash(self,session_key:str)->str|None:
        value=self._manifest().get("sessions",{}).get(session_key,{}).get("hash")
        return str(value) if value else None

    def prune(self,namespace:str)->dict:
        if namespace not in CACHE_LIMITS:raise ValueError("unknown cache namespace")
        directory=self.root/namespace;files=[item for item in directory.iterdir() if item.is_file() and item.name not in {"manifest.json"}]
        total=sum(item.stat().st_size for item in files);removed=0
        for item in sorted(files,key=lambda value:value.stat().st_atime):
            if total<=CACHE_LIMITS[namespace]:break
            size=item.stat().st_size;item.unlink(missing_ok=True);total-=size;removed+=1
        return {"namespace":namespace,"size_bytes":total,"limit_bytes":CACHE_LIMITS[namespace],"removed":removed}

    def diagnostics(self)->dict:
        result={}
        for name,limit in CACHE_LIMITS.items():
            size=sum(item.stat().st_size for item in (self.root/name).glob("**/*") if item.is_file());result[name]={"size_bytes":size,"limit_bytes":limit}
        result["total"]={"size_bytes":sum(item["size_bytes"] for item in result.values()),"limit_bytes":2*1024*1024*1024}
        return result
