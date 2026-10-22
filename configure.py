"""Interactive local Silra configuration. Never commit the generated .env file."""
from getpass import getpass
from pathlib import Path

root = Path(__file__).resolve().parent
print('ClinicPilot AI — Silra configuration')
key = getpass('Paste your NEW Silra API key (input hidden): ').strip()
if not key:
    raise SystemExit('No key entered; nothing changed.')
model = input('Silra model ID [deepseek-chat-fast]: ').strip() or 'deepseek-chat-fast'
if any(c in model for c in '\r\n'):
    raise SystemExit('Invalid model ID.')
path = root / '.env'
if path.exists():
    answer = input('.env already exists. Replace it? [y/N]: ').strip().lower()
    if answer != 'y':
        raise SystemExit('Existing configuration preserved.')
path.write_text(f'LLM_API_KEY={key}\nLLM_BASE_URL=https://api.silra.cn/v1\nLLM_MODEL={model}\n')
path.chmod(0o600)
print('Saved local .env (excluded from Git). Do not upload it.')
