import json
import os
from pathlib import Path
from typing import Any

def _collect_limits(data: dict[str, Any]) -> tuple[float, float, float, float]:
    drawing_facts = data.get("drawing_facts", {})
    bbox = data.get("bounding_box") or drawing_facts.get("bounding_box") or {}
    if all(k in bbox for k in ("min_x", "max_x", "min_y", "max_y")):
        return float(bbox["min_x"]), float(bbox["max_x"]), float(bbox["min_y"]), float(bbox["max_y"])

    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    geometry = data.get("geometry") or drawing_facts.get("geometry") or {}
    for ln in geometry.get("lines", []):
        min_x = min(min_x, float(ln["x1"]), float(ln["x2"]))
        max_x = max(max_x, float(ln["x1"]), float(ln["x2"]))
        min_y = min(min_y, float(ln["y1"]), float(ln["y2"]))
        max_y = max(max_y, float(ln["y1"]), float(ln["y2"]))
    for c in geometry.get("circles", []):
        cx, cy, r = float(c["cx"]), float(c["cy"]), float(c["r"])
        min_x, max_x = min(min_x, cx - r), max(max_x, cx + r)
        min_y, max_y = min(min_y, cy - r), max(max_y, cy + r)
    for a in geometry.get("arcs", []):
        cx, cy, r = float(a["cx"]), float(a["cy"]), float(a["r"])
        min_x, max_x = min(min_x, cx - r), max(max_x, cx + r)
        min_y, max_y = min(min_y, cy - r), max(max_y, cy + r)
    for poly in geometry.get("polylines", []):
        for point in poly.get("points", []):
            x = float(point[0])
            y = float(point[1])
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)

    if min_x == float("inf"):
        return 0.0, 1.0, 0.0, 1.0
    return min_x, max_x, min_y, max_y


def render_json_to_png(json_path: str, png_path: str, dpi: int = 300) -> None:
    os.environ.setdefault("MPLCONFIGDIR", str(Path(".matplotlib-cache").resolve()))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Arc, Circle

    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    geometry = data.get("geometry") or data.get("drawing_facts", {}).get("geometry") or {}

    out_path = Path(png_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(12, 9), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")

    for ln in geometry.get("lines", []):
        ax.plot(
            [float(ln["x1"]), float(ln["x2"])],
            [float(ln["y1"]), float(ln["y2"])],
            color="black",
            linewidth=0.7,
        )

    for c in geometry.get("circles", []):
        ax.add_patch(
            Circle((float(c["cx"]), float(c["cy"])), float(c["r"]), fill=False, color="black", linewidth=0.7)
        )

    for a in geometry.get("arcs", []):
        r = float(a["r"])
        ax.add_patch(
            Arc(
                (float(a["cx"]), float(a["cy"])),
                width=2 * r,
                height=2 * r,
                theta1=float(a["start_angle"]),
                theta2=float(a["end_angle"]),
                color="black",
                linewidth=0.7,
            )
        )

    for poly in geometry.get("polylines", []):
        points = poly.get("points", [])
        if len(points) < 2:
            continue
        xs = [float(p[0]) for p in points]
        ys = [float(p[1]) for p in points]
        if bool(poly.get("closed")):
            xs.append(float(points[0][0]))
            ys.append(float(points[0][1]))
        ax.plot(xs, ys, color="black", linewidth=0.7)

    for t in geometry.get("texts", []):
        text = str(t.get("text", "")).strip()
        if not text:
            continue
        x = float(t.get("x", 0.0))
        y = float(t.get("y", 0.0))
        rotation = float(t.get("rotation", 0.0))
        char_h = max(float(t.get("height", 2.5)), 1.0)
        font_size = max(5.0, min(12.0, char_h * 2.2))
        ax.text(
            x,
            y,
            text,
            color="black",
            fontsize=font_size,
            rotation=rotation,
            ha="left",
            va="bottom",
        )

    min_x, max_x, min_y, max_y = _collect_limits(data)
    pad_x = max((max_x - min_x) * 0.03, 1e-3)
    pad_y = max((max_y - min_y) * 0.03, 1e-3)
    ax.set_xlim(min_x - pad_x, max_x + pad_x)
    ax.set_ylim(min_y - pad_y, max_y + pad_y)

    fig.savefig(str(out_path), dpi=dpi, facecolor="white", bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
