"""Prestartup shim for comfyui_facetools_without_mediapipe.

Purpose
-------
setuptools >= 81 no longer ships ``pkg_resources``. On Windows,
``ctranslate2/__init__.py`` imports ``pkg_resources`` and uses
``pkg_resources.resource_filename("ctranslate2", "")`` exactly once to locate
its bundled DLLs (measured: this is the only pkg_resources usage in the
argostranslate import chain). Without it, ``argostranslate.translate`` fails
with ``ModuleNotFoundError: No module named 'pkg_resources'``, which breaks
the AlekPet ArgosTranslate nodes at ComfyUI startup.

This script registers a minimal, in-memory ``pkg_resources`` compatibility
shim *only* when the real pkg_resources is unavailable. It performs no
environment changes (no pip operations, no file writes outside this module).

Run by ComfyUI's prestartup phase (main.py: execute_prestartup_script), i.e.
before any custom node module is imported, so the shim is in place before
AlekPet/ArgosTranslate and ctranslate2 are imported.
"""

import importlib
import os
import sys
import types

_FLAG = "_comfyui_facetools_pkg_resources_shim"


def _install_pkg_resources_shim() -> bool:
    """Install a minimal pkg_resources shim if (and only if) it is missing.

    Returns True when a shim was installed, False when the real module is
    present or a shim is already registered.
    """
    if getattr(sys, _FLAG, False):
        return False

    try:
        importlib.import_module("pkg_resources")
        # Real pkg_resources exists (setuptools < 81): nothing to do.
        return False
    except ModuleNotFoundError:
        pass
    except Exception:
        # Unexpected error importing real pkg_resources; still provide shim.
        pass

    try:
        import importlib.util

        mod = types.ModuleType("pkg_resources")
        mod.__path__ = []  # mark as a package so submodules resolve cleanly

        def resource_filename(package_or_requirement, resource_name):
            """Return the on-disk directory/file for a package resource.

            Mirrors the common case used by ctranslate2: resolve a path
            relative to the importing package's directory.
            """
            # Split dotted package name and locate its directory via __file__.
            parts = str(package_or_requirement).split(".")
            candidate = parts[0] if parts else package_or_requirement
            try:
                pkg_mod = importlib.import_module(candidate)
            except Exception:
                # Fall back to the caller's directory.
                caller_dir = os.path.dirname(
                    sys._getframe(1).f_globals.get("__file__", os.getcwd())
                )
                return os.path.join(caller_dir, str(resource_name))

            base = os.path.dirname(os.path.abspath(getattr(pkg_mod, "__file__", os.getcwd())))
            # Subpackages: append remaining path components.
            for extra in parts[1:]:
                base = os.path.join(base, extra)
            return os.path.join(base, str(resource_name))

        def resource_listdir(package_or_requirement, resource_name):
            d = resource_filename(package_or_requirement, resource_name)
            try:
                return sorted(os.listdir(d))
            except OSError:
                return []

        def resource_exists(package_or_requirement, resource_name):
            return os.path.exists(resource_filename(package_or_requirement, resource_name))

        def resource_isdir(package_or_requirement, resource_name):
            return os.path.isdir(resource_filename(package_or_requirement, resource_name))

        def parse_version(v):
            try:
                from packaging.version import Version

                return Version(str(v))
            except Exception:
                return str(v)

        def parse_requirements(*args, **kwargs):
            """Yield nothing: requirement parsing is not needed at runtime."""
            return iter(())

        def get_distribution(name):
            """Return a minimal, duck-typed Distribution for metadata lookups."""

            class _Dist:
                def __init__(self, dist_name):
                    self.project_name = dist_name
                    self.key = str(dist_name).lower().replace("-", "_")
                    self.version = None
                    self.location = ""

                def __str__(self):
                    return f"{self.project_name} {self.version or '??'}"

                def __repr__(self):
                    return f"<pkg_resources.DistInfoDistribution {self}>"

                def has_metadata(self, name):
                    return False

                def get_metadata(self, name):
                    return ""

                def get_metadata_lines(self, name):
                    return iter(())

                def requires(self, *args, **kwargs):
                    return []

            name = str(getattr(name, "project_name", name))
            dist = _Dist(name)
            try:
                from importlib.metadata import version as _md_version

                dist.version = _md_version(name)
            except Exception:
                pass
            return dist

        def require(*args, **kwargs):
            return []

        def working_set(*_args, **_kwargs):
            return []

        # Expose a duck-typed working_set object (iterable + .require).
        class _WorkingSet(list):
            def require(self, *args, **kwargs):
                return []

            def find(self, req):
                try:
                    return get_distribution(getattr(req, "project_name", req))
                except Exception:
                    return None

            def iter_entry_points(self, group, name=None):
                return iter(())

        mod.resource_filename = resource_filename
        mod.resource_listdir = resource_listdir
        mod.resource_exists = resource_exists
        mod.resource_isdir = resource_isdir
        mod.parse_version = parse_version
        mod.parse_requirements = parse_requirements
        mod.get_distribution = get_distribution
        mod.require = require
        mod.working_set = _WorkingSet()
        mod.EntryPoint = getattr(sys.modules.get("pkg_resources"), "EntryPoint", object)
        mod.ResolutionError = type("ResolutionError", (Exception,), {})
        mod.VersionConflict = type("VersionConflict", (Exception,), {})
        mod.DistributionNotFound = type("DistributionNotFound", (Exception,), {})

        sys.modules["pkg_resources"] = mod
        sys.__dict__[_FLAG] = True
        print(
            "[comfyui_facetools] pkg_resources shim installed "
            "(setuptools>=81 removed pkg_resources; ctranslate2/argostranslate need it)"
        )
        return True
    except Exception as e:  # never break ComfyUI startup from a prestartup shim
        print(f"[comfyui_facetools] pkg_resources shim installation failed: {e}")
        return False


def main():
    _install_pkg_resources_shim()


main()
