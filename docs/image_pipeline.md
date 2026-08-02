# Image pipeline setup and acceptance

BookBuddy requires the packages in `requirements/requirements.txt` to start. The local image
pipeline is optional and degrades to structured evidence when its packages are
unavailable.

Install or check the optional packages explicitly:

```powershell
.\venv\Scripts\python.exe backend\dependency_manager.py --image --check
.\venv\Scripts\python.exe backend\dependency_manager.py --image --install
```

Pillow supplies image metadata and decoding, ImageHash supplies perceptual
near-duplicate hints, OpenCV supplies preprocessing, and PaddleOCR supplies
local OCR. Exact SHA-256 hashes remain the only cache identity. Perceptual
hashes are never cache keys.

Gemini Vision is disabled by default. A caller must authorize it explicitly,
and it is considered only after the local result is below the configured
confidence threshold. Vision output remains occurrence evidence and is not
stored in the source-independent parse cache.

Run automated verification with:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

Run the non-destructive local EPUB acceptance command against user-owned books:

```powershell
.\venv\Scripts\python.exe backend\image_pipeline_acceptance.py C:\path\to\book.epub
```

The acceptance command uses temporary databases and does not write to the
BookBuddy library.
