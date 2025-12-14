# backend/app/knowledge/build/print_env_versions.py
import sys

print("=== Runtime Environment Versions ===")

# Python
print(f"python: {sys.version.split()[0]}")

def safe_print(pkg_name, import_name=None, attr="__version__"):
    try:
        module = __import__(import_name or pkg_name)
        version = getattr(module, attr, "unknown")
        print(f"{pkg_name}: {version}")
    except Exception as e:
        print(f"{pkg_name}: not available ({e.__class__.__name__})")

safe_print("torch")
safe_print("faiss")
safe_print("transformers")
safe_print("sentence-transformers", import_name="sentence_transformers")
safe_print("numpy")
safe_print("scipy")

print("====================================")
