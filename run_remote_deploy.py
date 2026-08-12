import subprocess
import os
import sys

ip_list = ['ec2', '54.89.159.18', '34.235.119.76', '34.203.194.137']
success = False

for ip in ip_list:
    print(f"Trying IP: {ip}")
    try:
        # Check connection
        rc = subprocess.run(['ssh', '-o', 'ConnectTimeout=5', f'ubuntu@{ip}', 'echo SSH_OK'], capture_output=True, text=True)
        if 'SSH_OK' in rc.stdout:
            print(f"Connected to {ip}!")
            
            # Find directory
            dir_cmd = "if [ -d 'tastywork-trading-1' ]; then echo 'tastywork-trading-1'; elif [ -d 'tastywork-trading' ]; then echo 'tastywork-trading'; else echo 'none'; fi"
            rc = subprocess.run(['ssh', '-o', 'ConnectTimeout=5', f'ubuntu@{ip}', dir_cmd], capture_output=True, text=True)
            prj_dir = rc.stdout.strip()
            
            if prj_dir != 'none':
                print(f"Found project in ~/{prj_dir}. Deploying...")
                deploy_cmd = f"cd ~/{prj_dir} && git pull origin main && chmod +x deploy.sh && ./deploy.sh"
                rc = subprocess.run(['ssh', '-o', 'ConnectTimeout=60', f'ubuntu@{ip}', deploy_cmd], capture_output=True, text=True)
                
                with open('deploy_output.txt', 'w', encoding='utf-8') as f:
                    f.write(f"=== IP: {ip} ===\n")
                    f.write(f"=== PROJECT: {prj_dir} ===\n")
                    f.write("=== STDOUT ===\n")
                    f.write(rc.stdout)
                    f.write("\n=== STDERR ===\n")
                    f.write(rc.stderr)
                    f.write(f"\n=== EXIT CODE: {rc.returncode} ===\n")
                    
                success = True
                print("Deploy finished.")
                break
            else:
                print("Directory not found on this IP.")
    except Exception as e:
        print(f"Error on {ip}: {e}")

if not success:
    with open('deploy_output.txt', 'w', encoding='utf-8') as f:
        f.write("Failed to connect or find project directory on any IP.\n")
