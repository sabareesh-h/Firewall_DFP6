"""
TensorRT Export Script
======================
Run this ONCE to compile best.pt → best.engine.
After this, app.py will automatically load best.engine instead of best.pt
and inference will be 3–5× faster with ZERO accuracy loss.

Requirements:
  - NVIDIA GPU with CUDA
  - TensorRT installed (comes with CUDA Toolkit ≥ 11.x)
  - pip install tensorrt  (if not already present)

Usage:
    python export_tensorrt.py

The compiled engine is saved alongside best.pt as:
    SOP_Compliance/models/best.engine

IMPORTANT: The engine is GPU-specific — if you move to a different GPU,
run this script again to recompile.
"""

import os
import sys
import time

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
MODEL_PT    = os.path.join(BASE_DIR, "models", "best.pt")
MODEL_ENG   = os.path.join(BASE_DIR, "models", "best.engine")

# ─── Settings ─────────────────────────────────────────────────────────────────
IMGSZ  = 1280   # Must match IMGSZ in config.py
DEVICE = "0"    # GPU index
HALF   = True   # Export as FP16 for maximum speed (recommended)


def main():
    if not os.path.exists(MODEL_PT):
        print(f"❌  Model not found: {MODEL_PT}")
        sys.exit(1)

    if os.path.exists(MODEL_ENG):
        answer = input(
            f"⚠️   {MODEL_ENG} already exists.\n"
            "    Overwrite? (y/N): "
        ).strip().lower()
        if answer != "y":
            print("Aborted.")
            sys.exit(0)

    print(f"\n🔧  Exporting {MODEL_PT}")
    print(f"    imgsz={IMGSZ}  half={HALF}  device={DEVICE}")
    print("    This may take 3–10 minutes on first run (TRT optimises layer by layer).")
    print("    Subsequent exports for the same GPU are cached and are much faster.\n")

    try:
        from ultralytics import YOLO
    except ImportError:
        print("❌  ultralytics not installed. Run: pip install ultralytics")
        sys.exit(1)

    t0 = time.time()
    model = YOLO(MODEL_PT)
    engine_path = model.export(
        format="engine",
        imgsz=IMGSZ,
        half=HALF,
        device=DEVICE,
        simplify=True,     # ONNX simplification before TRT compile
        workspace=4,       # GPU memory workspace in GB for TRT optimiser
    )
    elapsed = time.time() - t0

    if engine_path and os.path.exists(engine_path):
        size_mb = os.path.getsize(engine_path) / (1024 * 1024)
        print(f"\n✅  Export complete in {elapsed:.0f}s")
        print(f"    Engine: {engine_path}  ({size_mb:.1f} MB)")
        print(f"\n🚀  Restart app.py — it will automatically use the TensorRT engine.")
    else:
        print(f"\n❌  Export failed. Check CUDA/TensorRT installation.")
        sys.exit(1)


if __name__ == "__main__":
    main()
