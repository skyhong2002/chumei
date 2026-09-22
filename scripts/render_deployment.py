#!/usr/bin/env python3
"""Render portable launchd/Caddy files without installing or starting services."""
import argparse
from pathlib import Path
import plistlib

ROOT = Path(__file__).resolve().parents[1]
OLD_ROOT = '/Users/skyhong/Projects/chumei'


def render(root, output, backup_destination):
    root, output, backup_destination = map(lambda p: Path(p).expanduser().resolve(), (root, output, backup_destination))
    if output.exists():
        raise ValueError('Output must be a new directory')
    output.mkdir(parents=True)

    def relocate(value):
        if isinstance(value, str):
            if value.startswith(OLD_ROOT):
                return str(root) + value[len(OLD_ROOT):]
            if value == '/Users/skyhong/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin':
                return str(Path.home() / '.local/bin') + ':/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'
        if isinstance(value, dict):
            return {k: relocate(v) for k, v in value.items()}
        if isinstance(value, list):
            return [relocate(v) for v in value]
        return value

    for template in (ROOT / 'deploy').glob('*.plist'):
        config = relocate(plistlib.loads(template.read_bytes()))
        (output / template.name).write_bytes(plistlib.dumps(config))
    for label, script, interval, extra in [
        ('telegram', 'publish_telegram.py', 1800, []),
        ('backup', 'backup_state.py', 3600, ['create', '--root', str(root), '--destination', str(backup_destination), '--keep', '168']),
    ]:
        name = 'tw.observe.chumei.' + label
        config = dict(Label=name, ProgramArguments=[str(root / '.venv/bin/python'), str(root / 'scripts' / script), *extra],
                      WorkingDirectory=str(root), EnvironmentVariables={'PYTHONUNBUFFERED': '1'},
                      StartInterval=interval, RunAtLoad=False, Umask=63,
                      StandardOutPath=str(root / 'state' / (label + '.log')), StandardErrorPath=str(root / 'state' / (label + '.log')))
        (output / (name + '.plist')).write_bytes(plistlib.dumps(config))
    (output / 'chumei.caddy').write_text((ROOT / 'deploy/chumei.caddy').read_text().replace(OLD_ROOT, str(root)))
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--backup-destination', type=Path, required=True)
    args = parser.parse_args()
    print(render(args.root, args.output, args.backup_destination))
