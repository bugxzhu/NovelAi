from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

PROMPTS_DIR = Path(__file__).parent

_env = Environment(
    loader=FileSystemLoader(str(PROMPTS_DIR)),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    autoescape=False,
)


def render(template_path: str, **variables) -> str:
    """Render a prompt template. Missing variables raise UndefinedError."""
    template = _env.get_template(template_path)
    return template.render(**variables)
