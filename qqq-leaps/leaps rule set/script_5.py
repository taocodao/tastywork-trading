
import shutil, os

os.makedirs('/home/user/output', exist_ok=True)

# Write pseudocode and python directly to output
pseudocode = open('/root/qqq_pmcc_pseudocode_v2.txt').read() if os.path.exists('/root/qqq_pmcc_pseudocode_v2.txt') else None

# Re-write from variables since /root is permission denied from Python too
with open('/home/user/output/qqq_pmcc_pseudocode_v2.txt', 'w') as f:
    f.write(open('/root/qqq_pmcc_pseudocode_v2.txt', 'r').read())
print("Pseudocode copied.")
