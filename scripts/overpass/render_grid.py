"""Vẽ bản đồ từ tọa độ mét đã xuất; cần Pillow, không cần QGIS trong tiến trình này."""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from project_paths import DATA_ROOT, project_file

ROOT = DATA_ROOT
data = json.loads((project_file(ROOT, "data/map_geometry.json")).read_text())
tiles = data["tiles"]
W, H = 1500, 1600
image = Image.new("RGB", (W, H), "#ffffff")
draw = ImageDraw.Draw(image)
font_path = "/System/Library/Fonts/Supplemental/Arial.ttf"
bold_path = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
title_font = ImageFont.truetype(bold_path, 35)
body_font = ImageFont.truetype(font_path, 23)
small_font = ImageFont.truetype(font_path, 19)
label_font = ImageFont.truetype(font_path, 13)
draw.text((75, 40), "HÀ NỘI — LƯỚI CHUẨN BỊ TẢI OVERPASS", fill="#15354a", font=title_font)
draw.text((75, 96), f"{len(tiles)} ô · cạnh ô gốc 5 km · EPSG:3405 · OSM tại 01/10/2026 00:00 UTC",
          fill="#4b6476", font=body_font)

xmin = min(t["rectangle"][0] for t in tiles)
ymin = min(t["rectangle"][1] for t in tiles)
xmax = max(t["rectangle"][2] for t in tiles)
ymax = max(t["rectangle"][3] for t in tiles)
left, top, right, bottom = 85, 190, W-85, H-310
scale = min((right-left)/(xmax-xmin), (bottom-top)/(ymax-ymin))
map_w, map_h = (xmax-xmin)*scale, (ymax-ymin)*scale
left += ((right-left)-map_w)/2
top += ((bottom-top)-map_h)/2


def xy(point):
    return left + (point[0]-xmin)*scale, top + (ymax-point[1])*scale


for tile in tiles:
    x1, y1, x2, y2 = tile["rectangle"]
    draw.rectangle([xy((x1, y2)), xy((x2, y1))], fill="#f0f5f8")

geometry = data["boundary"]
polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
for polygon in polygons:
    draw.polygon([xy(p) for p in polygon[0]], fill="#d7ece1")
    for hole in polygon[1:]:
        draw.polygon([xy(p) for p in hole], fill="#f0f5f8")

for tile in tiles:
    x1, y1, x2, y2 = tile["rectangle"]
    draw.rectangle([xy((x1, y2)), xy((x2, y1))], outline="#8aadc1", width=1)
    short = tile["tile_id"].removeprefix("HN_").replace("R", "").replace("_C", ",")
    draw.text(xy(((x1+x2)/2, (y1+y2)/2)), short, fill="#344d5c", font=label_font, anchor="mm")

for polygon in polygons:
    for ring in polygon:
        draw.line([xy(p) for p in ring], fill="#126f53", width=3)

# Mũi tên chỉ hướng bắc của lưới tọa độ chiếu.
ax, ay = W-90, 165
draw.text((ax, ay-28), "N", font=body_font, fill="#15354a", anchor="mm")
draw.line((ax, ay+55, ax, ay), fill="#15354a", width=3)
draw.polygon([(ax, ay), (ax-10, ay+20), (ax+10, ay+20)], fill="#15354a")
draw.text((W-145, ay+67), "Bắc lưới", font=small_font, fill="#4b6476")

legend_y = H-255
draw.rectangle((85, legend_y+5, 117, legend_y+28), fill="#d7ece1", outline="#126f53", width=2)
draw.text((133, legend_y), "Đa giác ranh giới Hà Nội từ OSM", font=body_font, fill="#15354a")
draw.rectangle((85, legend_y+48, 117, legend_y+71), fill="#f0f5f8", outline="#8aadc1", width=2)
draw.text((133, legend_y+43), "Ô vuông tải dữ liệu; nhãn là hàng,cột (đếm từ 0)", font=body_font, fill="#15354a")

sx, sy = W-465, legend_y+40
bar = 20000*scale
draw.line((sx, sy, sx+bar, sy), fill="#15354a", width=4)
draw.line((sx, sy-7, sx, sy+7), fill="#15354a", width=3)
draw.line((sx+bar, sy-7, sx+bar, sy+7), fill="#15354a", width=3)
draw.text((sx, sy+12), "0", font=small_font, fill="#15354a")
draw.text((sx+bar, sy+12), "20 km", font=small_font, fill="#15354a", anchor="ra")

draw.text((85, H-136), "Các ô ven ranh vẫn giữ hình vuông đầy đủ; lọc về Hà Nội sau khi tải và ghép dữ liệu.",
          font=small_font, fill="#4b6476")
draw.text((85, H-103), "Ranh này dùng để tổ chức tải; chưa được đối chiếu với lớp ranh pháp lý hoặc ranh LEZ.",
          font=small_font, fill="#4b6476")
draw.text((85, H-69), "Nguồn: © OpenStreetMap contributors · ODbL · relation 1903516",
          font=small_font, fill="#4b6476")
image.save(project_file(ROOT, "hanoi_download_grid.png"))
print(project_file(ROOT, "hanoi_download_grid.png"))
