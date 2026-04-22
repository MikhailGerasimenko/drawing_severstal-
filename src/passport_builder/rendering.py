import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(".matplotlib-cache").resolve()))

import ezdxf
from ezdxf.addons.drawing import matplotlib as ezdxf_matplotlib


def render_dxf_to_png(dxf_path: str, png_path: str, dpi: int = 300) -> None:
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    out_path = Path(png_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ezdxf_matplotlib.qsave(msp, str(out_path), dpi=dpi, bg="#FFFFFF", fg="#000000")
