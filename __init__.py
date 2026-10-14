# Auto-patch ReActor to permanently disable NSFW filter
try:
    from .patch_reactor import apply_patch as _apply_reactor_patch
    _apply_reactor_patch()
except Exception as _e:
    print(f"[comfyui_facetools] ReActor auto-patch initialization skipped: {_e}")

# In-memory runtime shim for albumentations / albucore version mismatch
# (Bypasses broken albumentations import chain by providing required Compose/Resize/Normalize/ToTensorV2
# directly in sys.modules, without modifying any installed site-packages files on disk)
def _setup_albumentations_shim():
    try:
        import sys
        import types

        # 1. In-memory fallback for albucore functions if albucore is missing attributes
        try:
            import albucore
            if not hasattr(albucore, "median_blur"):
                import cv2
                albucore.median_blur = lambda img, ksize: cv2.medianBlur(img, ksize)
            if not hasattr(albucore, "reduce_sum"):
                import numpy as np
                albucore.reduce_sum = lambda img, axis=None, keepdims=False: np.sum(img, axis=axis, keepdims=keepdims)
            if not hasattr(albucore, "apply_uint8_lut"):
                import cv2
                albucore.apply_uint8_lut = lambda img, lut: cv2.LUT(img, lut)
            if "albucore.filter3d" not in sys.modules:
                f3d = types.ModuleType("albucore.filter3d")
                f3d.gaussian_blur3d = lambda vol, ksize, sigma: vol
                sys.modules["albucore.filter3d"] = f3d
                albucore.filter3d = f3d
        except Exception:
            pass

        # 2. In-memory fallback for albumentations / albumentations.pytorch
        # If albumentations is already loaded and functional, preserve it
        if "albumentations" in sys.modules:
            existing_a = sys.modules["albumentations"]
            if hasattr(existing_a, "Compose") and hasattr(existing_a, "Resize") and hasattr(existing_a, "Normalize"):
                return

        # Attempt clean import without polluting sys.modules on error
        try:
            import albumentations as _test_a
            if hasattr(_test_a, "Compose") and hasattr(_test_a, "Resize") and hasattr(_test_a, "Normalize"):
                return
        except Exception:
            # Clean up failed partially-loaded modules from sys.modules
            for k in list(sys.modules.keys()):
                if k == "albumentations" or k.startswith("albumentations."):
                    sys.modules.pop(k, None)

        # Provide self-contained in-memory shim for InSPyReNet Remover transforms
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
    except Exception:
        pass

_setup_albumentations_shim()

from .nodes.nodes import *
from .InstantID import *

# Image Resize
try:
    from .nodes.image_resize import (
        NODE_CLASS_MAPPINGS as IMAGE_RESIZE_NODE_CLASS_MAPPINGS,
        NODE_DISPLAY_NAME_MAPPINGS as IMAGE_RESIZE_NODE_DISPLAY_NAME_MAPPINGS,
    )
except Exception as e:
    print(f"[comfyui_facetools] Failed to load image_resize: {e}")
    import traceback
    traceback.print_exc()
    IMAGE_RESIZE_NODE_CLASS_MAPPINGS = {}
    IMAGE_RESIZE_NODE_DISPLAY_NAME_MAPPINGS = {}

# Constrain Image
try:
    from .nodes.constrain_image import (
        NODE_CLASS_MAPPINGS as CONSTRAIN_IMAGE_NODE_CLASS_MAPPINGS,
        NODE_DISPLAY_NAME_MAPPINGS as CONSTRAIN_IMAGE_NODE_DISPLAY_NAME_MAPPINGS,
    )
except Exception as e:
    print(f"[comfyui_facetools] Failed to load constrain_image: {e}")
    import traceback
    traceback.print_exc()
    CONSTRAIN_IMAGE_NODE_CLASS_MAPPINGS = {}
    CONSTRAIN_IMAGE_NODE_DISPLAY_NAME_MAPPINGS = {}


# SAM3 removed: ComfyUI now supports SAM3 natively.

try:
    from .src.comfyui_facetools_disabled_mediapipe.insightface_segmentation import (
        NODE_CLASS_MAPPINGS as INSIGHTFACE_NODE_CLASS_MAPPINGS,
        NODE_DISPLAY_NAME_MAPPINGS as INSIGHTFACE_NODE_DISPLAY_NAME_MAPPINGS,
    )
except ImportError:
    INSIGHTFACE_NODE_CLASS_MAPPINGS = {}
    INSIGHTFACE_NODE_DISPLAY_NAME_MAPPINGS = {}

try:
    from .src.comfyui_facetools_disabled_mediapipe.face_mesh import (
        NODE_CLASS_MAPPINGS as FACE_MESH_NODE_CLASS_MAPPINGS,
        NODE_DISPLAY_NAME_MAPPINGS as FACE_MESH_NODE_DISPLAY_NAME_MAPPINGS,
    )
except ImportError:
    FACE_MESH_NODE_CLASS_MAPPINGS = {}
    FACE_MESH_NODE_DISPLAY_NAME_MAPPINGS = {}

# Face Parsing (integrated from nodes/face_parsing)
try:
    from .nodes.face_parsing import (
        NODE_CLASS_MAPPINGS as FACE_PARSING_NODE_CLASS_MAPPINGS,
    )
    FACE_PARSING_NODE_DISPLAY_NAME_MAPPINGS = {
        key: key for key in FACE_PARSING_NODE_CLASS_MAPPINGS
    }
except Exception as e:
    print(f"[comfyui_facetools] Failed to load face_parsing: {e}")
    import traceback
    traceback.print_exc()
    FACE_PARSING_NODE_CLASS_MAPPINGS = {}
    FACE_PARSING_NODE_DISPLAY_NAME_MAPPINGS = {}

# InSPyReNet Rembg (integrated from nodes/inspyrenet-rembg)
try:
    import importlib.util
    import os

    _inspyrenet_file = os.path.join(
        os.path.dirname(__file__), "nodes", "inspyrenet-rembg", "Inspyrenet_Rembg.py"
    )
    if os.path.exists(_inspyrenet_file):
        _spec = importlib.util.spec_from_file_location("inspyrenet_rembg", _inspyrenet_file)
        if _spec and _spec.loader:
            _setup_albumentations_shim()
            _inspyrenet_mod = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_inspyrenet_mod)
            INSPYRENET_REMBG_NODE_CLASS_MAPPINGS = {
                "InspyrenetRembg": _inspyrenet_mod.InspyrenetRembg,
                "InspyrenetRembgAdvanced": _inspyrenet_mod.InspyrenetRembgAdvanced,
            }
            INSPYRENET_REMBG_NODE_DISPLAY_NAME_MAPPINGS = {
                "InspyrenetRembg": "Inspyrenet Rembg",
                "InspyrenetRembgAdvanced": "Inspyrenet Rembg Advanced",
            }
        else:
            INSPYRENET_REMBG_NODE_CLASS_MAPPINGS = {}
            INSPYRENET_REMBG_NODE_DISPLAY_NAME_MAPPINGS = {}
    else:
        INSPYRENET_REMBG_NODE_CLASS_MAPPINGS = {}
        INSPYRENET_REMBG_NODE_DISPLAY_NAME_MAPPINGS = {}
except Exception as e:
    print(f"[comfyui_facetools] Failed to load inspyrenet_rembg: {e}")
    import traceback
    traceback.print_exc()
    INSPYRENET_REMBG_NODE_CLASS_MAPPINGS = {}
    INSPYRENET_REMBG_NODE_DISPLAY_NAME_MAPPINGS = {}

NODE_CLASS_MAPPINGS = {
    'DetectFaces': DetectFaces,
    'DetectFaceByIndex': DetectFaceByIndex,
    'CropFaces': CropFaces,
    'WarpFacesBack': WarpFaceBack,
    "SelectFloatByBool": SelectFloatByBool,


    "InstantIDModelLoader": InstantIDModelLoader,
    "InstantIDFaceAnalysis": InstantIDFaceAnalysis,
    "ApplyInstantID": ApplyInstantID,
    "SaveFaceEmbeds": SaveFaceEmbeds,
    "LoadFaceEmbeds": LoadFaceEmbeds,

    "VAEDecodeNew": VAEDecodeNew,
    "VAEEncodeNew": VAEEncodeNew,

    'ColorAdjustNew(FaceParsing)': ColorAdjust,

    "SaveImageWebsocketNew": SaveImageWebsocket,

}

# Add Image Resize nodes
NODE_CLASS_MAPPINGS.update(IMAGE_RESIZE_NODE_CLASS_MAPPINGS)

# Add Constrain Image nodes
NODE_CLASS_MAPPINGS.update(CONSTRAIN_IMAGE_NODE_CLASS_MAPPINGS)

# Add InsightFace segmentation nodes
NODE_CLASS_MAPPINGS.update(INSIGHTFACE_NODE_CLASS_MAPPINGS)

# Add Face Mesh nodes
NODE_CLASS_MAPPINGS.update(FACE_MESH_NODE_CLASS_MAPPINGS)

# Add Face Parsing nodes
NODE_CLASS_MAPPINGS.update(FACE_PARSING_NODE_CLASS_MAPPINGS)

# Add InSPyReNet Rembg nodes
NODE_CLASS_MAPPINGS.update(INSPYRENET_REMBG_NODE_CLASS_MAPPINGS)

NODE_DISPLAY_NAME_MAPPINGS = {
    'DetectFaces': 'DetectFaces',
    'DetectFaceByIndex': 'Detect Face By Index',
    'CropFaces': 'CropFaces',
    'WarpFacesBack': 'Warp Faces Back',
    "SelectFloatByBool": "Select Float (Bool)",

    "InstantIDModelLoader": "Load InstantID Model",
    "InstantIDFaceAnalysis": "InstantID Face Analysis",
    "ApplyInstantID": "Apply InstantID",
    "SaveFaceEmbeds": "Save Face Embeds",
    "LoadFaceEmbeds": "Load Face Embeds",

    "VAEDecodeNew": "VAE Decode New",
    "VAEEncodeNew": "VAE Encode New",

    'ColorAdjustNew(FaceParsing)': 'Color Adjust (Face Parsing) New',
    "SaveImageWebsocketNew": "Save Image Websocket New To JPG",

}

# Add Image Resize node display names
NODE_DISPLAY_NAME_MAPPINGS.update(IMAGE_RESIZE_NODE_DISPLAY_NAME_MAPPINGS)

# Add Constrain Image node display names
NODE_DISPLAY_NAME_MAPPINGS.update(CONSTRAIN_IMAGE_NODE_DISPLAY_NAME_MAPPINGS)

# Add InsightFace segmentation node display names
NODE_DISPLAY_NAME_MAPPINGS.update(INSIGHTFACE_NODE_DISPLAY_NAME_MAPPINGS)

# Add Face Mesh node display names
NODE_DISPLAY_NAME_MAPPINGS.update(FACE_MESH_NODE_DISPLAY_NAME_MAPPINGS)

# Add Face Parsing node display names
NODE_DISPLAY_NAME_MAPPINGS.update(FACE_PARSING_NODE_DISPLAY_NAME_MAPPINGS)

# Add InSPyReNet Rembg node display names
NODE_DISPLAY_NAME_MAPPINGS.update(INSPYRENET_REMBG_NODE_DISPLAY_NAME_MAPPINGS)


# Load ComfyUI frontend extensions (e.g. COLORCODE widget)
WEB_DIRECTORY = "./js"

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']
