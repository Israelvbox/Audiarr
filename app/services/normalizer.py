import re
import unicodedata


FORBIDDEN_CHARS = re.compile(r'[<>:"/\\|?*]')
MULTI_SPACE = re.compile(r" {2,}")


def normalize_name(name: str) -> str:
    """Convierte '  arDo   440!! ' en 'Ardo 440'."""
    name = unicodedata.normalize("NFKC", name)
    name = FORBIDDEN_CHARS.sub("", name)
    name = name.strip()
    name = MULTI_SPACE.sub(" ", name)
    name = name.title()
    return name


def sanitize_path_component(component: str) -> str:
    """Para nombres de carpeta/archivo, más agresivo."""
    name = FORBIDDEN_CHARS.sub("", component)
    name = MULTI_SPACE.sub(" ", name)
    return name.strip(". ")
