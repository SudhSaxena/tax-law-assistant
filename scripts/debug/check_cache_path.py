import os

print("Current working directory:", os.getcwd())
print("cache.db resolves to:", os.path.abspath("cache.db"))
print("File exists at that path:", os.path.exists("cache.db"))