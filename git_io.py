"""Portable Git snapshots. Never checkout or modify a user's working tree."""
import base64
import hashlib
import os
from pathlib import Path
from urllib.parse import urlparse
import re
import subprocess

MAX_BUNDLE = 48 * 1024 * 1024


def command(args, cwd=None, **kwargs):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=180,
                            env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'}, **kwargs)
    if result.returncode:
        raise ValueError((result.stderr or result.stdout or 'command failed')[-3000:])
    return result.stdout.strip()


def git(*args, cwd):
    return command(['git', *args], cwd=cwd)


def validate_remote(url):
    parsed = urlparse(url or '')
    if parsed.scheme in ('http', 'https') and (parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError('Repository URL must not contain credentials, query parameters or fragments')
    return url


def inspect_repo(value):
    path = Path(value).expanduser().resolve(strict=True)
    root = Path(git('rev-parse', '--show-toplevel', cwd=path)).resolve()
    head = git('rev-parse', 'HEAD', cwd=root)
    branch = git('symbolic-ref', '--quiet', '--short', 'HEAD', cwd=root)
    dirty = bool(git('status', '--porcelain', '--untracked-files=normal', cwd=root))
    try:
        remote = validate_remote(git('remote', 'get-url', 'origin', cwd=root))
    except ValueError:
        remote = ''
    try:
        base = git('symbolic-ref', '--short', 'refs/remotes/origin/HEAD', cwd=root).removeprefix('origin/')
    except ValueError:
        base = branch
    return dict(local_path=str(root), name=root.name, base_sha=head, base_ref=base,
                branch=branch, repo_url=remote, dirty=dirty)


def encode_bundle(path):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_BUNDLE:
        raise ValueError('Git bundle exceeds 48 MiB; use a configured remote Workspace for this repository')
    return {'data': base64.b64encode(raw).decode(), 'sha256': hashlib.sha256(raw).hexdigest()}


def decode_bundle(value, path):
    raw = base64.b64decode(value['data'], validate=True)
    if len(raw) > MAX_BUNDLE or hashlib.sha256(raw).hexdigest() != value['sha256']:
        raise ValueError('Git bundle size or SHA-256 mismatch')
    Path(path).write_bytes(raw)


def snapshot(path, output):
    info = inspect_repo(path)
    if info['dirty']:
        raise ValueError('工作目录有未提交改动，请先提交后再运行；系统不会自动修改或忽略这些改动。')
    git('bundle', 'create', str(output), 'HEAD', cwd=info['local_path'])
    if inspect_repo(path)['base_sha'] != info['base_sha'] or inspect_repo(path)['dirty']:
        raise ValueError('Repository changed during snapshot; submit again')
    return info, encode_bundle(output)


def github_repo(url):
    match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([\w.-]+/[\w.-]+?)(?:\.git)?/?', url or '')
    return match.group(1) if match else None
