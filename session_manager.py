import asyncio
from copy import deepcopy


class SessionManager:
    def __init__(self):
        self.sessions = {}
        self.book_locks = {}
        self.analysis_tasks = {}

    def set_book(self, session_key: str, book):
        self.sessions[session_key] = book
        self.book_locks.setdefault(session_key, asyncio.Lock())

    def get_book(self, session_key: str):
        return self.sessions.get(session_key)

    def get_lock(self, session_key: str):
        self.book_locks.setdefault(session_key, asyncio.Lock())
        return self.book_locks[session_key]

    def get_task(self, session_key: str, default: dict | None = None) -> dict:
        if session_key not in self.analysis_tasks:
            return deepcopy(default) if default is not None else {}
        return deepcopy(self.analysis_tasks[session_key])

    def set_task(self, session_key: str, state: dict):
        self.analysis_tasks[session_key] = state

    def update_task(self, session_key: str, **updates):
        self.analysis_tasks.setdefault(session_key, {})
        self.analysis_tasks[session_key].update(updates)

    def request_cancel(self, session_key: str) -> bool:
        task = self.analysis_tasks.get(session_key)
        if not task or task.get("status") != "processing":
            return False
        task["cancel_requested"] = True
        task["log"] = "Cancellation requested. Waiting for current chapter to finish."
        return True

    def cancel_requested(self, session_key: str) -> bool:
        return bool(self.analysis_tasks.get(session_key, {}).get("cancel_requested"))
