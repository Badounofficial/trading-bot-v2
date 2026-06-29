"""Configuration loader. Reads config.yaml once and exposes it as a dict."""
from pathlib import Path
import yaml

CONFIG_PATH = Path(__file__).parent / 'config.yaml'

def load_config(path=CONFIG_PATH) -> dict:
    """Load YAML config. Returns a nested dict."""
    with open(path) as f:
        return yaml.safe_load(f)


# Lazy singleton
_cfg = None
def cfg() -> dict:
    """Cached config accessor."""
    global _cfg
    if _cfg is None:
        _cfg = load_config()
    return _cfg


if __name__ == '__main__':
    import json
    print(json.dumps(load_config(), indent=2, default=str))
