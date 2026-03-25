"""
generators/base.py - Base Jinja2 renderer shared by all generators.
"""

from __future__ import annotations
import os
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, StrictUndefined


def _get_env() -> Environment:
    templates_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "templates"
    )
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    return env


def render(template_name: str, **context) -> str:
    """Render a template with given context, always injecting timestamp."""
    env = _get_env()
    tmpl = env.get_template(template_name)
    context.setdefault('timestamp', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return tmpl.render(**context)


def write(path: str, content: str) -> None:
    """Write ASCII content to file, enforcing no non-ASCII characters."""
    try:
        content.encode('ascii')
    except UnicodeEncodeError as e:
        raise ValueError(f"Non-ASCII in generated content for {path}: {e}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='ascii') as f:
        f.write(content)
