"""Provider registry. To add one: write a module with a Provider subclass and add it to MODULES."""
import importlib
from .base import Provider

MODULES = ["claude", "chatgpt", "copilot", "cursor", "gemini", "zai", "kimi", "minimax", "mistral", "devtools",
           "webcookie", "credits", "more_api", "more_subs", "more_web", "litellm", "windsurf"]

REGISTRY = {}
for _m in MODULES:
    _mod = importlib.import_module(f".{_m}", __name__)
    for _v in vars(_mod).values():
        if isinstance(_v, type) and issubclass(_v, Provider) and _v is not Provider and _v.__module__ == _mod.__name__ \
                and getattr(_v, "id", "?") != "?":
            REGISTRY[_v.id] = _v()
