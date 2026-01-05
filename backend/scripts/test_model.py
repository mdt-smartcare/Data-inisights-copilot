import torch
from sentence_transformers import SentenceTransformer
import os

print("Torch version:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())
print("MPS available:", torch.backends.mps.is_available())

model_path = './models/bge-m3'
print("Model path exists:", os.path.exists(model_path))

try:
    model = SentenceTransformer(model_path, device='cpu')
    print("Model loaded successfully!")
    test_text = "This is a test sentence."
    embedding = model.encode(test_text)
    print("Embedding shape:", embedding.shape)
except Exception as e:
    print("Error loading model:", str(e))