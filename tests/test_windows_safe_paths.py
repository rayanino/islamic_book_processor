from ibp.config import sanitize_path_component


def test_windows_reserved_name_is_suffixed():
    assert sanitize_path_component("CON") == "CON_"


def test_invalid_windows_chars_are_replaced():
    cleaned = sanitize_path_component('bad<>:"/\\|?*name. ')
    assert cleaned == "bad_________name"


def test_empty_component_defaults_to_unnamed():
    assert sanitize_path_component("   ") == "unnamed"
