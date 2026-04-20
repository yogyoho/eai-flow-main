#!/usr/bin/env python3
import os
import stat
import shutil

# Git Bash home is /home/test which maps to C:\Users\test on Windows
nginx_src = r'C:\Users\admin\AppData\Local\Microsoft\WinGet\Packages\freenginx.nginx_Microsoft.Winget.Source_8wekyb3d8bbwe\freenginx-1.29.7'
bash_home = r'C:\Users\test'  # Git Bash home maps here

# Create ~/bin directory
home_bin = os.path.join(bash_home, 'bin')
os.makedirs(home_bin, exist_ok=True)
print(f'Created directory: {home_bin}')

# Create nginx wrapper script
nginx_wrapper = os.path.join(home_bin, 'nginx')
wrapper_content = '#!/bin/bash\nexec "/mnt/c/Users/admin/AppData/Local/Microsoft/WinGet/Packages/freenginx.nginx_Microsoft.Winget.Source_8wekyb3d8bbwe/freenginx-1.29.7/nginx.exe" "$@"\n'
with open(nginx_wrapper, 'w') as f:
    f.write(wrapper_content)
os.chmod(nginx_wrapper, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
print(f'Created nginx wrapper: {nginx_wrapper}')

# Copy nginx.exe to ~/bin
src_exe = os.path.join(nginx_src, 'nginx.exe')
dst_exe = os.path.join(home_bin, 'nginx.exe')
shutil.copy2(src_exe, dst_exe)
print(f'Copied nginx.exe to: {dst_exe}')

# Add PATH to ~/.bashrc
bashrc_path = os.path.join(bash_home, '.bashrc')
marker = 'export PATH="$HOME/bin:$PATH"'
if os.path.exists(bashrc_path):
    with open(bashrc_path, 'r') as f:
        content = f.read()
    if marker not in content:
        with open(bashrc_path, 'a') as f:
            f.write(f'\n{marker}\n')
        print(f'Updated .bashrc with PATH')
else:
    with open(bashrc_path, 'w') as f:
        f.write(f'\n{marker}\n')
    print(f'Created .bashrc with PATH')

print('Done!')
