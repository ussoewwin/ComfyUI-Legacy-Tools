import os
import sys
import re
import builtins
import logging

logger = logging.getLogger("comfyui_facetools")

PATCH_MARKER = "# NSFW filter disabled by comfyui_facetools"

SFW_REPLACEMENT_CODE = '''"""Auto-patched by comfyui_facetools to disable NSFW filter"""
from PIL import Image
import io
import logging
import os
import comfy.model_management as model_management
from scripts.reactor_logger import logger

MODEL_EXISTS = True

def ensure_nsfw_model(nsfwdet_model_path):
    """NSFW filter disabled by comfyui_facetools"""
    return True

SCORE = 0.979

def nsfw_image(img_data, model_path: str):
    """NSFW filter disabled by comfyui_facetools - always returns False (safe)"""
    return False
'''


def get_possible_reactor_dirs():
    candidates = []
    # 1. Direct standard ComfyUI path
    hardcoded = r"D:\USERFILES\ComfyUI\ComfyUI\custom_nodes\ComfyUI-ReActor"
    if os.path.isdir(hardcoded):
        candidates.append(os.path.abspath(hardcoded))

    # 2. Check relative to folder_paths if available
    try:
        import folder_paths
        if hasattr(folder_paths, "base_path"):
            p = os.path.join(folder_paths.base_path, "custom_nodes", "ComfyUI-ReActor")
            if os.path.isdir(p):
                candidates.append(os.path.abspath(p))
    except Exception:
        pass

    # 3. Check relative to current file's custom_nodes parent directory
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    p_sibling = os.path.join(base_dir, "ComfyUI-ReActor")
    if os.path.isdir(p_sibling):
        candidates.append(os.path.abspath(p_sibling))

    # Remove duplicates preserving order
    unique_candidates = []
    for c in candidates:
        if c not in unique_candidates:
            unique_candidates.append(c)

    return unique_candidates


def patch_reactor_files(reactor_dir: str):
    patched_any = False

    # 1. Patch scripts/reactor_sfw.py
    sfw_path = os.path.join(reactor_dir, "scripts", "reactor_sfw.py")
    if os.path.isfile(sfw_path):
        try:
            with open(sfw_path, "r", encoding="utf-8") as f:
                sfw_content = f.read()

            if "NSFW filter disabled by comfyui_facetools" not in sfw_content:
                with open(sfw_path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(SFW_REPLACEMENT_CODE)
                print(f"[Facetools] Successfully patched: {sfw_path} (NSFW filter disabled)")
                patched_any = True
        except Exception as e:
            print(f"[Facetools] Error patching {sfw_path}: {e}")

    # 2. Patch nodes.py to bypass loop and overhead
    nodes_path = os.path.join(reactor_dir, "nodes.py")
    if os.path.isfile(nodes_path):
        try:
            with open(nodes_path, "r", encoding="utf-8") as f:
                nodes_content = f.read()

            nsfw_pattern = re.compile(
                r"[ \t]*# NSFW checker\r?\n"
                r"[\s\S]*?"
                r"[ \t]*progress_bar_reset\(pbar\)\r?\n?",
                re.MULTILINE
            )

            if nsfw_pattern.search(nodes_content):
                new_content = nsfw_pattern.sub(
                    "        # NSFW checker bypassed by comfyui_facetools\n",
                    nodes_content
                )
                with open(nodes_path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(new_content)
                print(f"[Facetools] Successfully patched: {nodes_path} (NSFW loop bypassed)")
                patched_any = True
        except Exception as e:
            print(f"[Facetools] Error patching {nodes_path}: {e}")

    return patched_any


def patch_reactor_runtime():
    """Hook sys.modules and import mechanism in case ReActor is loaded in memory"""
    def _neutralize(module):
        try:
            if hasattr(module, "nsfw_image"):
                module.nsfw_image = lambda *args, **kwargs: False
            if hasattr(module, "ensure_nsfw_model"):
                module.ensure_nsfw_model = lambda *args, **kwargs: True
        except Exception:
            pass

    # Neutralize any already loaded modules
    for name, mod in list(sys.modules.items()):
        if mod is not None and ("reactor_sfw" in name or name.endswith("sfw")):
            _neutralize(mod)

    # Wrap builtins.__import__ to neutralize as soon as reactor_sfw is imported
    orig_import = builtins.__import__

    def hooked_import(name, globals=None, locals=None, fromlist=(), level=0):
        mod = orig_import(name, globals, locals, fromlist, level)
        if "reactor_sfw" in name or (fromlist and any("reactor_sfw" in str(x) for x in fromlist)):
            _neutralize(mod)
            if hasattr(mod, "reactor_sfw"):
                _neutralize(getattr(mod, "reactor_sfw"))
        if "albumentations" in name or "albucore" in name:
            try:
                if "albumentations" not in sys.modules or not hasattr(sys.modules["albumentations"], "Compose"):
                    import types
                    import numpy as np
                    import torch
                    import cv2

                    a_mod = types.ModuleType("albumentations")
                    ap_mod = types.ModuleType("albumentations.pytorch")

                    class Compose:
                        def __init__(self, transforms, **kwargs):
                            self.transforms = [t for t in transforms if t is not None]

                        def __call__(self, image=None, **kwargs):
                            res = image if image is not None else kwargs.get("img")
                            for t in self.transforms:
                                if hasattr(t, "apply_to_image"):
                                    res = t.apply_to_image(res)
                                elif callable(t):
                                    try:
                                        out = t(image=res)
                                        res = out["image"] if isinstance(out, dict) and "image" in out else out
                                    except TypeError:
                                        res = t(res)
                            return {"image": res}

                    class Resize:
                        def __init__(self, height, width, **kwargs):
                            self.height = int(height)
                            self.width = int(width)

                        def __call__(self, image=None, **kwargs):
                            img = image if image is not None else kwargs.get("img")
                            if img is not None:
                                img = cv2.resize(img, (self.width, self.height), interpolation=cv2.INTER_LINEAR)
                            return {"image": img}

                    class Normalize:
                        def __init__(self, mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225), max_pixel_value=255.0, **kwargs):
                            self.mean = np.array(mean, dtype=np.float32)
                            self.std = np.array(std, dtype=np.float32)
                            self.max_pixel_value = float(max_pixel_value)

                        def __call__(self, image=None, **kwargs):
                            img = image if image is not None else kwargs.get("img")
                            if img is not None:
                                img = img.astype(np.float32) / self.max_pixel_value
                                img = (img - self.mean) / self.std
                            return {"image": img}

                    class ToTensorV2:
                        def __init__(self, transpose_mask=False, **kwargs):
                            self.transpose_mask = transpose_mask

                        def __call__(self, image=None, **kwargs):
                            img = image if image is not None else kwargs.get("img")
                            if img is not None:
                                if img.ndim == 3:
                                    img = img.transpose(2, 0, 1)
                                elif img.ndim == 2:
                                    img = img[np.newaxis, ...]
                                t = torch.from_numpy(img)
                            else:
                                t = None
                            return {"image": t}

                    a_mod.Compose = Compose
                    a_mod.Resize = Resize
                    a_mod.Normalize = Normalize
                    ap_mod.ToTensorV2 = ToTensorV2
                    a_mod.pytorch = ap_mod

                    sys.modules["albumentations"] = a_mod
                    sys.modules["albumentations.pytorch"] = ap_mod
                    if name == "albumentations":
                        return a_mod
                    if name == "albumentations.pytorch":
                        return ap_mod
            except Exception:
                pass
        return mod

    builtins.__import__ = hooked_import


def apply_patch():
    """Main entrypoint executed on node import"""
    try:
        # Runtime hook
        patch_reactor_runtime()

        # Disk files patch
        dirs = get_possible_reactor_dirs()
        for d in dirs:
            patch_reactor_files(d)
    except Exception as e:
        print(f"[Facetools] Warning: Failed to apply ReActor NSFW patch: {e}")
