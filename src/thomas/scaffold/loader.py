"""Template loader for scaffold package using importlib.resources."""

from importlib.resources import files


def load_template(template_name: str) -> str:
    """
    Load a scaffold template file by name.

    Args:
        template_name: Relative path to template within scaffold package
                      (e.g., "config/environments/example.json.dist")

    Returns:
        Template file contents as string

    Raises:
        BrokenInstallationError: If templates cannot be resolved via importlib.resources
    """
    try:
        scaffold_dir = files("thomas.scaffold")
        template_path = template_name.split("/")
        resource = scaffold_dir
        for part in template_path:
            resource = resource.joinpath(part)
        return resource.read_text(encoding="utf-8")
    except (FileNotFoundError, AttributeError, TypeError) as e:
        from .errors import BrokenInstallationError
        raise BrokenInstallationError(
            "Scaffold templates not found. Reinstall: pip install --force-reinstall the-thomas-test-suite"
        ) from e
