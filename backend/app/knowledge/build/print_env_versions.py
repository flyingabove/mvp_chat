import torch
import faiss
import transformers
import sentence_transformers
import numpy
import scipy

print("=== Runtime Environment Versions ===")
print(f"python: (runtime)")
print(f"torch: {torch.__version__}")
print(f"faiss: {faiss.__version__}")
print(f"transformers: {transformers.__version__}")
print(f"sentence-transformers: {sentence_transformers.__version__}")
print(f"numpy: {numpy.__version__}")
print(f"scipy: {scipy.__version__}")
print("====================================")
