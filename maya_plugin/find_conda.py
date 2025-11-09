"""Find conda installation in WSL"""
import subprocess

print("Searching for conda in WSL...")
print()

# Try to find conda
cmd = ['wsl', 'bash', '-c', 'which conda 2>/dev/null || echo "not found in PATH"']
result = subprocess.run(cmd, capture_output=True, text=True)
print("Conda location:", result.stdout.strip())

# Try common locations
locations = [
    '~/miniconda3',
    '~/anaconda3',
    '/opt/conda',
    '/opt/miniconda3',
    '/usr/local/miniconda3',
    '~/.conda'
]

print("\nChecking common conda locations:")
for loc in locations:
    cmd = ['wsl', 'bash', '-c', f'ls -d {loc} 2>/dev/null && echo "EXISTS" || echo "not found"']
    result = subprocess.run(cmd, capture_output=True, text=True)
    status = "FOUND" if "EXISTS" in result.stdout else "not found"
    print(f"  {loc}: {status}")

# Check for conda environments
print("\nLooking for conda environments:")
cmd = ['wsl', 'bash', '-c', 'find ~ -name "envs" -type d 2>/dev/null | grep conda']
result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
if result.stdout:
    print(result.stdout)
else:
    print("  No conda envs folders found")

print("\nTry activating conda manually in WSL and run:")
print("  wsl bash -c 'conda env list'")
