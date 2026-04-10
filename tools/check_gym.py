import sys, os
print("Python:", sys.executable)
try:
    import gymnasium
    print("gymnasium OK:", gymnasium.__version__)
except ImportError as e:
    print("gymnasium FAIL:", e)

print("sys.path[:5]:", sys.path[:5])
