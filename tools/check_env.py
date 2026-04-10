import sys
out = []
out.append(f"Python: {sys.executable}")

packages = ['torch', 'gymnasium', 'numpy', 'matlab']
for pkg in packages:
    try:
        mod = __import__(pkg)
        out.append(f"{pkg}: OK {getattr(mod, '__version__', '?')}")
    except ImportError as e:
        out.append(f"{pkg}: MISSING ({e})")

with open(r'C:\Users\27443\Desktop\Multi-Agent  VSGs\results\harness\env_check_result.txt', 'w') as f:
    f.write('\n'.join(out) + '\n')

print('\n'.join(out))
