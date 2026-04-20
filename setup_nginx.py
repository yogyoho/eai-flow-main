#!/usr/bin/env python3
"""Create nginx wrapper for Git Bash on Windows."""

import os
import stat

# Git Bash home is /home/test which maps to C:\Users\test on Windows
# Write using Unix-style paths (bash understands them)
home = '/home/test'
bin_dir = os.path.join(home, 'bin')
os.makedirs(bin_dir, exist_ok=True)

# Create nginx wrapper script
nginx_wrapper = os.path.join(bin_dir, 'nginx')
wrapper_content = '''#!/bin/bash
exec "/mnt/c/Users/admin/AppData/Local/Microsoft/WinGet/Packages/freenginx.nginx_Microsoft.Winget.Source_8wekyb3d8bbwe/freenginx-1.29.7/nginx.exe" "$@"
'''

with open(nginx_wrapper, 'w', newline='\n') as f:
    f.write(wrapper_content)

os.chmod(nginx_wrapper, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
print(f'Created nginx wrapper: {nginx_wrapper}')

# Add PATH to .bashrc
bashrc = os.path.join(home, '.bashrc')
marker = 'export PATH="$HOME/bin:$PATH"'
if os.path.exists(bashrc):
    with open(bashrc, 'r') as f:
        content = f.read()
    if marker not in content:
        with open(bashrc, 'a') as f:
            f.write(f'\n{marker}\n')
        print('Updated .bashrc with PATH')
    else:
        print('.bashrc already has PATH')
else:
    with open(bashrc, 'w') as f:
        f.write(f'\n{marker}\n')
    print(f'Created .bashrc with PATH')

print('Done!')
