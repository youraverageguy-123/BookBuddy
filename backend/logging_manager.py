import json
import os
from datetime import datetime

def utc_timestamp() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")

def session_dir_from_db_dir(db_dir: str) -> str:
    return os.path.dirname(os.path.abspath(db_dir))

def session_log_dir(db_dir: str) -> str:
    log_dir = os.path.join(session_dir_from_db_dir(db_dir), "logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir

def write_prompt_log(db_dir: str, chapter_index: int, prompt: str, metadata: dict) -> str:
    prompts_dir = os.path.join(session_log_dir(db_dir), "prompts")
    os.makedirs(prompts_dir, exist_ok=True)
    path = os.path.join(prompts_dir, f"chapter_{chapter_index}_{utc_timestamp()}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(metadata, indent=2, ensure_ascii=False))
        f.write("\n\n")
        f.write(prompt)
    return path

def write_response_log(db_dir: str, chapter_index: int, response_text: str, metadata: dict) -> str:
    responses_dir = os.path.join(session_log_dir(db_dir), "responses")
    os.makedirs(responses_dir, exist_ok=True)
    path = os.path.join(responses_dir, f"chapter_{chapter_index}_{utc_timestamp()}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"metadata": metadata, "response": response_text}, f, indent=2, ensure_ascii=False)
    return path

def append_failure_log(db_dir: str, metadata: dict, error: str, prompt: str, response_info: str = ""):
    path = os.path.join(session_log_dir(db_dir), "failures.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n" + "=" * 100 + "\n")
        f.write(json.dumps({**metadata, "error": error, "response_info": response_info}, indent=2, ensure_ascii=False))
        f.write("\n\nPROMPT_PREVIEW:\n")
        f.write(prompt[:10000])
        f.write("\n")

def append_analysis_log(db_dir: str, event: dict):
    path = os.path.join(session_log_dir(db_dir), "analysis.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"timestamp": datetime.utcnow().isoformat(), **event}, ensure_ascii=False))
        f.write("\n")
