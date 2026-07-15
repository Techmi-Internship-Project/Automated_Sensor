import re

from config import load_app_settings, save_app_settings

def is_valid_name(name) :
    """
    Returns True only if name uses letters, numbers, underscores, or hyphens
    """
    return re.fullmatch(r"[A-Za-z0-9_-]+", name) is not None

def get_media_type_options() :
    """
    Finds the names of all media types the user has entered before.

    Unlike organisms (one folder per type under training/), media types have
    no folder of their own — run.json just carries a media_type string that
    the partner ML machine reads. The list of previously used values is
    persisted in app_settings.json so the dropdown can offer them again.
    """

    settings = load_app_settings()
    return sorted(settings.get("known_media_types", []))


def add_media_type_option(name) :
    """
    Persists a newly created media type so it appears in future dropdowns.
    """

    settings = load_app_settings()
    known = set(settings.get("known_media_types", []))
    known.add(name)
    settings["known_media_types"] = sorted(known)
    save_app_settings(settings)
