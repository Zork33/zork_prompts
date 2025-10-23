#!/usr/bin/env python3
"""
extract_upper_scheme.py

Extract the upper (white-background) floorplan from a PDF page and produce:
 - a cropped PNG of the upper scheme
 - a preview PNG showing crop + polygon + detected openings/door arcs over the page
 - a JSON describing polygon (crop coords and page coords), openings, door arcs

Usage:
    python extract_upper_scheme.py /path/to/page-6.pdf /path/to/outdir

Dependencies:
    pip install pymupdf pillow opencv-python numpy

Notes:
    - The script chooses the top-most large non-white region on the page as the "upper scheme".
    - Coordinates in JSON are pixels (page-level and crop-level). Verify results visually.

"""
import sys
from pathlib import Path
import json
import math

from PIL import Image, ImageDraw
import numpy as np

# require PyMuPDF and OpenCV
try:
    import fitz  # PyMuPDF
except Exception as e:
    raise SystemExit("PyMuPDF (fitz) is required: pip install pymupdf")

try:
    import cv2
except Exception as e:
    raise SystemExit("OpenCV is required: pip install opencv-python")


def find_top_region_and_crop(img_pil, white_thresh=245, min_area=200, pad=20, debug=False):
    """Return crop box (x0,y0,x1,y1) in page pixels for the top-most non-white region."""
    img_rgb = img_pil.convert("RGB")
    np_img = np.array(img_rgb)
    # luminosity
    brightness = (0.299 * np_img[:, :, 0] + 0.587 * np_img[:, :, 1] + 0.114 * np_img[:, :, 2])
    nonwhite_mask = (brightness < white_thresh).astype(np.uint8) * 255

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask_clean = cv2.morphologyEx(nonwhite_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask_clean = cv2.morphologyEx(mask_clean, cv2.MORPH_OPEN, kernel, iterations=1)

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask_clean, connectivity=8)
    candidates = []
    for i in range(1, num_labels):
        x, y, ww, hh, area = stats[i]
        cx, cy = centroids[i]
        if area < min_area:
            continue
        candidates.append({"label": int(i), "bbox": [int(x), int(y), int(ww), int(hh)], "area": int(area), "centroid": [float(cx), float(cy)]})

    if not candidates:
        raise RuntimeError("No non-white regions found on page. Adjust white_thresh or check PDF rendering.")

    # choose the candidate with smallest centroid y (uppermost)
    candidates_sorted = sorted(candidates, key=lambda c: c["centroid"][1])
    top = candidates_sorted[0]
    x, y, ww, hh = top["bbox"]
    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(img_rgb.size[0], x + ww + pad)
    y1 = min(img_rgb.size[1], y + hh + pad)
    if debug:
        print(f"Top candidate bbox: {top['bbox']}, crop=({x0},{y0},{x1},{y1})")
    return (x0, y0, x1, y1)


def extract_contours_from_crop(crop_pil, min_component_area=100, approx_epsilon_factor=0.01):
    """Return main polygon (approx) and list of other contours (with bbox + area + center) in crop-local coords."""
    np_crop = np.array(crop_pil.convert("RGB"))
    gray = cv2.cvtColor(np_crop, cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    th = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 21, 9)
    kernel2 = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    morph = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel2, iterations=2)

    nb, labs, stats, cents = cv2.connectedComponentsWithStats(morph, connectivity=8)
    clean = np.zeros_like(morph)
    for i in range(1, nb):
        if stats[i, cv2.CC_STAT_AREA] >= min_component_area:
            clean[labs == i] = 255

    contours, _ = cv2.findContours(clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, []

    contours_sorted = sorted(contours, key=lambda c: cv2.contourArea(c), reverse=True)
    main_cnt = contours_sorted[0]
    peri = cv2.arcLength(main_cnt, True)
    approx = cv2.approxPolyDP(main_cnt, approx_epsilon_factor * peri, True)
    main_poly = [[int(p[0][0]), int(p[0][1])] for p in approx]

    others = []
    mx, my, mw, mh = cv2.boundingRect(main_cnt)
    for cnt in contours_sorted[1:]:
        area = int(cv2.contourArea(cnt))
        if area < 50:
            continue
        bx, by, bw, bh = cv2.boundingRect(cnt)
        cx = bx + bw / 2
        cy = by + bh / 2
        touch_edge = (bx <= mx + 5) or (by <= my + 5) or (bx + bw >= mx + mw - 5) or (by + bh >= my + mh - 5)
        if touch_edge or area < 2000:
            others.append({
                "bbox": [int(bx), int(by), int(bw), int(bh)],
                "area": int(area),
                "center": [int(cx), int(cy)],
            })
    return main_poly, others


def detect_door_arcs(crop_pil, contours, area_min=300, area_max=8000, std_ratio_thresh=0.35, coverage_min_deg=20, coverage_max_deg=260):
    """Analyze contours and return those that look like arcs (door swings)."""
    np_crop = np.array(crop_pil.convert("RGB"))
    gray = cv2.cvtColor(np_crop, cv2.COLOR_RGB2GRAY)
    out_arcs = []
    for cnt in contours:
        area = int(cv2.contourArea(cnt))
        if area < area_min or area > area_max:
            continue
        pts = cnt.reshape(-1, 2)
        (cx_c, cy_c), r = cv2.minEnclosingCircle(pts)
        dists = np.sqrt(((pts[:, 0] - cx_c) ** 2 + (pts[:, 1] - cy_c) ** 2))
        mean_dist = float(dists.mean())
        std_dist = float(dists.std())
        if mean_dist <= 3 or std_dist / mean_dist >= std_ratio_thresh:
            continue
        angs = np.arctan2(pts[:, 1] - cy_c, pts[:, 0] - cx_c)
        angs_un = np.unwrap(np.sort(angs))
        coverage = float(angs_un[-1] - angs_un[0])
        coverage_deg = math.degrees(coverage)
        if coverage_deg > coverage_min_deg and coverage_deg < coverage_max_deg:
            out_arcs.append({
                "center_px": [float(round(cx_c, 1)), float(round(cy_c, 1))],
                "radius_px": float(round(mean_dist, 1)),
                "coverage_deg": float(round(coverage_deg, 1)),
            })
    return out_arcs


def make_preview_images(page_img, crop_box, main_poly_page, openings_page, door_arcs_page, out_dir: Path):
    """Save crop image and a page preview with overlays."""
    x0, y0, x1, y1 = crop_box
    crop = page_img.crop((x0, y0, x1, y1))
    crop_p = out_dir / "upper_scheme_crop.png"
    crop.save(crop_p)

    # preview on full page
    vis = page_img.convert("RGB")
    draw = ImageDraw.Draw(vis)
    draw.rectangle([x0, y0, x1, y1], outline="lime", width=3)
    if main_poly_page:
        pts = [tuple(p) for p in main_poly_page]
        draw.line(pts + [pts[0]], fill="red", width=4)
    for op in openings_page:
        bx, by, bw, bh = op["bbox_page"]
        draw.rectangle([bx, by, bx + bw, by + bh], outline="blue", width=2)
    for da in door_arcs_page:
        cx, cy = da["center_page"]
        r = da["radius_px"]
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline="orange", width=2)
    preview_p = out_dir / "page_upper_scheme_preview.png"
    vis.save(preview_p)
    return crop_p, preview_p


def main(argv):
    if len(argv) < 3:
        print("Usage: python extract_upper_scheme.py /path/to/page.pdf /output/dir")
        return 2
    pdf_path = Path(argv[1])
    out_dir = Path(argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    # Render first page (index 0)
    doc = fitz.open(str(pdf_path))
    page = doc.load_page(0)
    zoom = 2.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    page_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    # find crop for top-most scheme
    crop_box = find_top_region_and_crop(page_img)
    x0, y0, x1, y1 = crop_box
    crop = page_img.crop(crop_box)

    # extract contours and openings in crop-local coords
    main_poly_crop, openings_crop = extract_contours_from_crop(crop)
    # get full contours list for arc detection
    # re-run contours on cleaned binary to get raw contours
    np_crop = np.array(crop.convert("RGB"))
    gray = cv2.cvtColor(np_crop, cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    th = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 21, 9)
    kernel2 = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    morph = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel2, iterations=2)
    contours, _ = cv2.findContours(morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    door_arcs_crop = detect_door_arcs(crop, contours)

    # convert crop-local coords to page coords
    main_poly_page = [[int(px + x0), int(py + y0)] for px, py in (main_poly_crop or [])]
    openings_page = []
    for op in openings_crop:
        bx, by, bw, bh = op["bbox"]
        openings_page.append({"bbox_page": [int(bx + x0), int(by + y0), int(bw), int(bh)], "center_page": [int(op["center"][0] + x0), int(op["center"][1] + y0)], "area": int(op["area"])})
    door_arcs_page = []
    for da in door_arcs_crop:
        cx, cy = da["center_px"]
        door_arcs_page.append({"center_page": [float(round(cx + x0, 1)), float(round(cy + y0, 1))], "radius_px": float(da["radius_px"]), "coverage_deg": float(da["coverage_deg"])})

    # save outputs
    out_json = {
        "source_pdf": str(pdf_path),
        "page_index": 0,
        "crop_bbox_page": [int(x0), int(y0), int(x1 - x0), int(y1 - y0)],
        "apartment_outline_crop": main_poly_crop,
        "apartment_outline_page": main_poly_page,
        "openings_crop": openings_crop,
        "openings_page": openings_page,
        "door_arcs_crop": door_arcs_crop,
        "door_arcs_page": door_arcs_page,
        "notes": "Auto-extracted; verify coordinates visually."
    }
    out_json_path = out_dir / f"{pdf_path.stem}_upper_scheme_extraction.json"
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(out_json, f, ensure_ascii=False, indent=2)

    crop_p, preview_p = make_preview_images(page_img, crop_box, main_poly_page, openings_page, door_arcs_page, out_dir)

    print("Wrote:")
    print(" - JSON:", out_json_path)
    print(" - Crop PNG:", crop_p)
    print(" - Preview PNG:", preview_p)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
