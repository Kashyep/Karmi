"""Save Clerk client and JWT verification settings privately; never print keys."""
from __future__ import annotations

import base64
import getpass
import os
import re
import warnings
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def write_private_env(path: Path, values: dict[str, str]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        stream.write('# Private Clerk development configuration. Never commit this file.\n')
        for key, value in values.items():
            quoted = value.replace('\\', '\\\\').replace("'", "\\'")
            stream.write(f"{key}='{quoted}'\n")


def main() -> int:
    path = ROOT / '.env.clerk'
    if path.exists() or path.is_symlink():
        print('Existing .env.clerk preserved. No changes made.')
        return 1
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            publishable = getpass.getpass('Paste Clerk Publishable Key (hidden): ').strip()
            issuer = getpass.getpass('Paste Clerk Frontend API URL / JWT issuer (hidden): ').strip()
            print('Paste every line of Clerk JWT Public Key PEM. Submit a blank line when finished.')
            pem_lines: list[str] = []
            while True:
                line = getpass.getpass('JWT public key line (hidden; blank ends input): ')
                if not line:
                    break
                pem_lines.append(line)
        pem = '\n'.join(pem_lines).strip() + '\n'
        parsed = urlparse(issuer)
        if (not re.fullmatch(r'pk_(test|live)_[A-Za-z0-9_-]+', publishable)
                or parsed.scheme != 'https' or not parsed.netloc
                or '-----BEGIN PUBLIC KEY-----' not in pem
                or '-----END PUBLIC KEY-----' not in pem):
            raise ValueError('Invalid Clerk key or issuer format.')
        values = {
            'DAILY_AGENT_CLERK_PUBLISHABLE_KEY': publishable,
            'DAILY_AGENT_CLERK_ISSUER': issuer.rstrip('/'),
            'DAILY_AGENT_CLERK_JWT_PUBLIC_KEY_B64': base64.b64encode(pem.encode()).decode(),
        }
        write_private_env(path, values)
    except (ValueError, OSError, EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print('Setup stopped. Check key format and terminal permissions; no key values displayed.')
        return 1
    print('Saved private .env.clerk with owner-only permissions. No Clerk API call was made.')
    print('Do not paste key values into chat or commit this file.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
