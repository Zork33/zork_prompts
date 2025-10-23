Parsed apartment plan package.

Included:
- parsed_plan.json : auto-extracted JSON scene (best-effort). Check "scale_reference" in JSON; if px_to_mm is null, provide a known dimension to rescale.
- parsed_plan.svg  : SVG overlay showing detected numbers (red) and entrance (green).
- 7.1 2Д.png        : original source image.

Next steps:
- If you want accurate metric dimensions, provide one known measurement from the drawing (e.g., "6250" mm). I will rescale and regenerate precise walls/openings in meters.
- To request a glTF export or floorplan JSON adjusted to specific schema, tell me and I'll produce it.

Generated automatically.
