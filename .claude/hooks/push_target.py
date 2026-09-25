"""Decide whether a Bash command pushes to the beta branch.

Used by pre_push_beta_rebase.sh. Reads the PreToolUse JSON on stdin and the
current branch from $BRANCH; prints one of: skip | rebase | deny-prod.
Kept as its own file so the detection is testable without running git.
"""
import json, os, re, shlex, sys

try:
    cmd = json.load(sys.stdin).get('tool_input', {}).get('command', '') or ''
except Exception:
    cmd = ''
branch = os.environ.get('BRANCH', '')


def push_targets(segment):
    try:
        tokens = shlex.split(segment, posix=True)
    except ValueError:
        tokens = segment.split()
    if 'git' not in tokens:
        return None
    rest = tokens[tokens.index('git') + 1:]
    # skip git global options such as -C <dir> / -c k=v
    while rest and rest[0].startswith('-'):
        rest = rest[2:] if rest[0] in ('-C', '-c') else rest[1:]
    if not rest or rest[0] != 'push':
        return None
    args = [a for a in rest[1:] if not a.startswith('-')]
    refspecs = args[1:]                      # args[0] is the remote
    if not refspecs:
        return [branch]
    targets = []
    for spec in refspecs:
        dest = spec.lstrip('+').split(':')[-1] or spec
        dest = dest.replace('refs/heads/', '')
        targets.append(branch if dest == 'HEAD' else dest)
    return targets


targets = []
for segment in re.split(r'&&|\|\||;|\||\n', cmd):
    found = push_targets(segment)
    if found:
        targets += found

if 'beta' not in targets:
    print('skip')
elif branch == 'prod':
    print('deny-prod')
else:
    print('rebase')
