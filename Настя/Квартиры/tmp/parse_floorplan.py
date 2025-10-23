#!/usr/bin/env python3
"""
parse_floorplan.py

Usage:
    python parse_floorplan.py --image "/path/to/7.1 2Д.png" [--scale_mm 6250] [--out /tmp/plan_out]

Outputs:
    - <out>/parsed_plan.json
    - <out>/parsed_plan.svg

Notes:
    - Requires: python3, pip install opencv-python numpy pillow pytesseract shapely
    - Also requires system tesseract (e.g., apt install tesseract-ocr / brew install tesseract)
    - This is a robust heuristic parser — manual verification recommended.
"""
import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import pytesseract

# Optional: shapely for geometry convenience (if installed)
try:
    from shapely.geometry import Polygon, LineString, Point
except Exception:
    Polygon = None
    LineString = None
    Point = None

def ocr_numbers(img_pil):
    """Return list of detected numeric tokens with bounding boxes using pytesseract."""
    data = pytesseract.image_to_data(img_pil, output_type=pytesseract.Output.DICT, lang='rus+eng')
    nums = []
    for i, txt in enumerate(data['text']):
        t = txt.strip().replace(',', '.')
        if not t:
            continue
        # numeric pattern
        try:
            if t.replace('.', '', 1).isdigit():
                x, y, w, h = (data['left'][i], data['top'][i], data['width'][i], data['height'][i])
                nums.append({'text': t, 'bbox': [int(x), int(y), int(w), int(h)],
                             'center': [int(x + w/2), int(y + h/2)]})
        except Exception:
            continue
    return nums

def image_preprocess_for_contours(cv_img):
    """Convert to binary image tuned for architectural drawings."""
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    # Remove small color noise but keep edges
    bl = cv2.bilateralFilter(gray, 9, 75, 75)
    # Adaptive threshold to get lines
    th = cv2.adaptiveThreshold(bl, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY_INV, 15, 7)
    # Morph close to join lines
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))
    morph = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel, iterations=1)
    return morph

def find_main_contours(bin_img, min_area_ratio=0.01):
    """Find contours and return sorted by area (largest first)."""
    contours, _ = cv2.findContours(bin_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = bin_img.shape[:2]
    min_area = w * h * min_area_ratio
    big = [cnt for cnt in contours if cv2.contourArea(cnt) > min_area]
    big_sorted = sorted(big, key=lambda c: cv2.contourArea(c), reverse=True)
    return big_sorted

def approx_polygon_from_contour(cnt, epsilon_factor=0.01):
    peri = cv2.arcLength(cnt, True)
    approx = cv2.approxPolyDP(cnt, epsilon_factor * peri, True)
    pts = [(int(p[0][0]), int(p[0][1])) for p in approx]
    return pts

def project_point_to_segment(px, py, ax, ay, bx, by):
    # project point p onto segment ab, return projection point and t in [0,1]
    vx, vy = bx-ax, by-ay
    wx, wy = px-ax, py-ay
    denom = vx*vx + vy*vy
    if denom == 0:
        return (ax, ay), 0.0
    t = (vx*wx + vy*wy) / denom
    t_clamped = max(0.0, min(1.0, t))
    projx = ax + vx * t_clamped
    projy = ay + vy * t_clamped
    return (projx, projy), t_clamped

def detect_openings_from_small_contours(contours_all, wall_poly, px_to_mm=None, min_bbox_dim=10):
    """
    Heuristic: find thin short contours (door/window symbols) and map them to nearest wall edge.
    contours_all: all contours from binary image (not only external).
    wall_poly: list of ordered vertices for outer wall polygon.
    Returns: list of openings with wall_idx, t_pos (0..1 along edge), width_m
    """
    openings = []
    if not wall_poly or len(wall_poly) < 2:
        return openings
    # Precompute edges
    edges = []
    for i in range(len(wall_poly)):
        a = wall_poly[i]
        b = wall_poly[(i+1)%len(wall_poly)]
        edges.append((i, a, b))
    # For each contour, filter by small size (potential door/window glyph)
    for cnt in contours_all:
        x,y,w,h = cv2.boundingRect(cnt)
        if w < min_bbox_dim and h < min_bbox_dim:
            continue
        # a typical opening glyph is rectangular and small (<200 px)
        if w > 10 and h > 10 and w < 400 and h < 400:
            cx = x + w/2
            cy = y + h/2
            # find nearest edge
            best = None
            for (idx, a, b) in edges:
                (projx, projy), t = project_point_to_segment(cx, cy, a[0], a[1], b[0], b[1])
                dist = math.hypot(projx - cx, projy - cy)
                if best is None or dist < best[0]:
                    best = (dist, idx, t, (a,b))
            if best and best[0] < 40:  # within 40 px of edge
                # convert width to meters if scale exists (use larger bbox dimension)
                width_px = max(w, h)
                width_m = (width_px * px_to_mm / 1000.0) if px_to_mm else None
                openings.append({
                    "bbox_px": [int(x), int(y), int(w), int(h)],
                    "wall_idx": int(best[1]),
                    "t_on_edge": float(best[2]),
                    "width_m": round(width_m,3) if width_m else None,
                    "center_px": [int(cx), int(cy)]
                })
    return openings

def poly_px_to_meters(poly_px, px_to_mm):
    if px_to_mm is None:
        return None
    return [[round((x * px_to_mm)/1000.0, 3), round((y * px_to_mm)/1000.0, 3)] for (x,y) in poly_px]

def save_json(out_path, data):
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def svg_from_json(json_data, out_svg_path, image_path=None):
    """Render a simple SVG floorplan from JSON structure."""
    # Compute canvas size from original image if present
    w = json_data.get("image_size_px", {}).get("width_px", 1000)
    h = json_data.get("image_size_px", {}).get("height_px", 1000)
    walls = json_data.get("walls_px") or []
    openings = json_data.get("openings") or []
    scale_text = f"scale: {json_data.get('scale_info', {}).get('px_to_mm')} px->mm" if json_data.get('scale_info') else ""
    # Build SVG
    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">')
    if image_path:
        svg.append(f'<image href="file://{image_path}" x="0" y="0" width="{w}" height="{h}" opacity="0.3"/>')
    # draw walls polygon
    for wall in walls:
        pts = wall.get("polyline_px")
        if not pts:
            continue
        pts_str = " ".join([f'{x},{y}' for (x,y) in pts])
        svg.append(f'<polyline points="{pts_str}" fill="none" stroke="#000" stroke-width="6" stroke-linejoin="round"/>')
    # draw openings as small red rectangles / gaps
    for op in openings:
        bx,by,bw,bh = op.get("bbox_px", [0,0,0,0])
        svg.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" fill="none" stroke="red" stroke-width="2"/>')
        if op.get("width_m"):
            svg.append(f'<text x="{bx+2}" y="{by+bh+12}" font-size="12" fill="red">{op["width_m"]}m</text>')
    # annotate scale
    svg.append(f'<text x="10" y="{h-10}" font-size="14" fill="#333">{scale_text}</text>')
    svg.append('</svg>')
    Path(out_svg_path).write_text("\n".join(svg), encoding="utf-8")
    return out_svg_path

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--image", required=True, help="path to floorplan image (PNG/JPG)")
    p.add_argument("--scale_mm", type=float, default=None, help="reference dimension in mm (optional). If provided, used to compute px->mm")
    p.add_argument("--out", default="./plan_out", help="output directory")
    args = p.parse_args()

    img_path = Path(args.image)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load image
    cv_img = cv2.imread(str(img_path))
    if cv_img is None:
        raise SystemExit("Cannot open image: " + str(img_path))
    h_img, w_img = cv_img.shape[:2]

    # OCR: try to find numeric tokens for auto-scaling
    pil = Image.open(str(img_path)).convert("RGB")
    nums = ocr_numbers(pil)
    px_to_mm = None
    scale_used = None
    if args.scale_mm:
        # user-provided scale: use it relative to the largest horizontal numeric bbox width or ask to supply pixel segment later
        scale_used = float(args.scale_mm)
        # find the numeric with largest bbox width (heuristic)
        if nums:
            largest = max(nums, key=lambda n: n['bbox'][2])
            px_ref = largest['bbox'][2]
            if px_ref > 0:
                px_to_mm = scale_used / px_ref
    else:
        # if OCR found a big numeric that is plausible (>=1000), use it as mm for that token width
        if nums:
            # choose numeric token whose value >= 1000 and has largest bbox width
            numeric_candidates = [n for n in nums if float(n['text']) >= 1000]
            if numeric_candidates:
                largest = max(numeric_candidates, key=lambda n: n['bbox'][2])
                scale_used = float(largest['text'])
                px_ref = largest['bbox'][2]
                if px_ref > 0:
                    px_to_mm = scale_used / px_ref

    # Preprocess and contour detection
    bin_img = image_preprocess_for_contours(cv_img)
    big_contours = find_main_contours(bin_img, min_area_ratio=0.002)
    walls_poly_px = None
    if big_contours:
        # take largest external contour and approximate polygon
        main_cnt = big_contours[0]
        poly = approx_polygon_from_contour(main_cnt, epsilon_factor=0.01)
        walls_poly_px = poly
    # Also get all contours to search openings
    all_contours, _ = cv2.findContours(bin_img, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    openings = detect_openings_from_small_contours(all_contours, walls_poly_px or [], px_to_mm=px_to_mm)

    # Build JSON
    scene = {
        "meta": {
            "title": img_path.stem,
            "source_image": str(img_path),
            "units": "meters" if px_to_mm else "pixels",
            "notes": "Auto-parsed; verify walls and openings manually."
        },
        "image_size_px": {"width_px": w_img, "height_px": h_img},
        "detected_numbers_ocr": nums,
        "scale_info": {
            "px_to_mm": px_to_mm,
            "scale_value_mm": scale_used
        },
    }
    if walls_poly_px:
        scene["walls_px"] = [{"id": "outer", "polyline_px": walls_poly_px}]
        scene["walls_m"] = None
        if px_to_mm:
            scene["walls_m"] = [{"id": "outer", "polyline_m": poly_px_to_meters(walls_poly_px, px_to_mm)}]
    scene["openings"] = openings

    # Save JSON
    out_json = out_dir / "parsed_plan.json"
    save_json(out_json, scene)

    # Create SVG (overlay)
    out_svg = out_dir / "parsed_plan.svg"
    svg_from_json(scene, out_svg, image_path=str(img_path))

    print("Saved JSON:", out_json)
    print("Saved SVG:", out_svg)
    if px_to_mm:
        print(f"Scale auto-detected: 1 px = {px_to_mm:.4f} mm  (reference {scale_used} mm).")
    else:
        print("No reliable scale detected. Provide --scale_mm <mm> referencing a numeric label on the image (e.g., 6250).")

if __name__ == "__main__":
    main()
