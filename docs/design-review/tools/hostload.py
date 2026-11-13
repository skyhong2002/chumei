"""Wait for room on a shared host before building or opening a browser.

Used by build_preview.py and capture.py. Works on Linux (/proc/meminfo) and
macOS (vm_stat). Limits: CM_MAX_LOAD (load1, default 10) and CM_MIN_MEM_GIB
(available memory, default 1).
"""
import os
import re
import shutil
import subprocess
import time

MAX_LOAD = float(os.environ.get('CM_MAX_LOAD', '10'))
MIN_MEM_GIB = float(os.environ.get('CM_MIN_MEM_GIB', '1'))


def mem_available_gib():
    if os.path.exists('/proc/meminfo'):
        with open('/proc/meminfo') as info:
            for line in info:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1]) / 1024 / 1024
        return 99.0
    try:
        out = subprocess.check_output(['vm_stat'], text=True)
    except (OSError, subprocess.CalledProcessError):
        return 99.0
    page = int(re.search(r'page size of (\d+) bytes', out).group(1))
    pages = {m.group(1): int(m.group(2)) for m in re.finditer(r'^Pages (free|inactive|speculative|purgeable):\s+(\d+)', out, re.M)}
    return sum(pages.values()) * page / 1024 ** 3


def wait_for_load(pause=60):
    while os.getloadavg()[0] > MAX_LOAD or mem_available_gib() < MIN_MEM_GIB:
        print(f'load1 {os.getloadavg()[0]:.1f}, available {mem_available_gib():.1f} GiB; waiting', flush=True)
        time.sleep(pause)


def low_priority(command):
    """Prefix a command with nice, plus ionice where the host has it (Linux)."""
    prefix = ['nice', '-n', '15']
    if shutil.which('ionice'):
        prefix += ['ionice', '-c3']
    return prefix + command
