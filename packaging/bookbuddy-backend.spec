# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path(SPEC).resolve().parent.parent
source_root = root / "backend"
wn_data_root = Path(os.environ.get("WN_DATA_DIR", Path.home() / ".wn_data"))
wn_database = wn_data_root / "wn.db"
if not wn_database.is_file():
    raise SystemExit("Open English WordNet data is missing. Run: python -m wn download oewn:2024")

datas = [
    (str(root / "requirements" / "requirements*.txt"), "requirements"),
    (str(root / "config" / "version.json"), "config"),
    (str(wn_database), "wn_data"),
]
binaries = []
hiddenimports = ["app", "uvicorn.logging", "uvicorn.loops.asyncio", "uvicorn.protocols.http.h11_impl", "uvicorn.lifespan.on", "multipart", "pdf_parser", "pypdf"]
for package in ("wn", "cmudict", "en_core_web_sm"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

analysis = Analysis([str(source_root / "main.py")], pathex=[str(source_root)], binaries=binaries, datas=datas, hiddenimports=hiddenimports, hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, analysis.binaries, analysis.datas, [], name="bookbuddy-backend", debug=False, bootloader_ignore_signals=False, strip=False, upx=True, console=False)
