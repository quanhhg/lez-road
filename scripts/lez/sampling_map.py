"""Render measured GIS sampling outputs; never invent or alter geographic geometry."""
from __future__ import annotations

import json
from pathlib import Path

from .common import WORK, atomic_json, file_hash, input_path, now, relative


def render(work=WORK):
    if (Path(work)/'config/sampling_abc.json').is_file():
        from .export_route_maps import export_maps
        export_maps(work)
        return Path(work)/'maps/routes/60_tuyen_LEZ2030.png'

    from .gis import initialize
    from qgis.core import (QgsVectorLayer,QgsFillSymbol,QgsLineSymbol,QgsMapSettings,
                           QgsMapRendererParallelJob,QgsCategorizedSymbolRenderer,QgsRendererCategory)
    from qgis.PyQt.QtCore import QSize
    from qgis.PyQt.QtGui import QColor,QImage,QPainter,QFont
    work=Path(work);initialize(work)
    report=json.loads((work/'reports/sampling/latest_sampling_2030.json').read_text())
    zones=input_path(work,report['paths']['zones']);routes=input_path(work,report['paths']['routes'])
    def layer(name,style):
        value=QgsVectorLayer(str(zones)+'|layername='+name,name,'ogr')
        if not value.isValid():raise ValueError('Cannot render '+name)
        value.renderer().setSymbol(QgsFillSymbol.createSimple(style));return value
    hanoi=layer('hanoi',{'color':'#f7f7f4','outline_color':'#868e96','outline_width':'0.3'})
    inside=layer('sampling_inside',{'color':'#c8e4ef','outline_color':'#559ac0','outline_width':'0.2'})
    reference=layer('reference_lez_2030',{'color':'0,0,0,0','outline_color':'#4f3e81','outline_style':'dash','outline_width':'0.5'})
    added=layer('added_inside',{'color':'#fac57f','outline_color':'#d1801b','outline_width':'0.15'})
    removed=layer('removed_inside',{'color':'#dbc5e0','outline_color':'#886493','outline_width':'0.15'})
    route_layer=QgsVectorLayer(str(routes)+'|layername=candidate_routes','routes','ogr')
    if not route_layer.isValid():raise ValueError('Cannot render routes')
    route_layer.setRenderer(QgsCategorizedSymbolRenderer('group',[
        QgsRendererCategory('inside',QgsLineSymbol.createSimple({'line_color':'#176ea5','line_width':'0.6'}),'Trong'),
        QgsRendererCategory('outside',QgsLineSymbol.createSimple({'line_color':'#178560','line_width':'0.55'}),'Ngoài')]))
    def draw(layers,extent,width,height):
        setting=QgsMapSettings();setting.setLayers(layers);setting.setDestinationCrs(hanoi.crs())
        extent.scale(1.08);setting.setExtent(extent);setting.setOutputSize(QSize(width,height));setting.setBackgroundColor(QColor('white'))
        job=QgsMapRendererParallelJob(setting);job.start();job.waitForFinished();return job.renderedImage()
    canvas=QImage(1900,1250,QImage.Format.Format_ARGB32);canvas.fill(QColor('#ffffff'))
    painter=QPainter(canvas);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor('#1b344b'));painter.setFont(QFont('Arial',25,QFont.Weight.Bold))
    painter.drawText(45,55,'LEZ 2030 · PHẠM VI LẤY MẪU VÀ 60 TUYẾN ỨNG VIÊN')
    painter.setFont(QFont('Arial',13));painter.drawText(45,92,'20 tuyến trong / 40 tuyến ngoài · bản chụp đường OSM 01/10/2026 · dân cư WorldPop mô hình hóa năm 2025')
    painter.setFont(QFont('Arial',15,QFont.Weight.Bold));painter.drawText(55,145,'Toàn Hà Nội — các tuyến đã sinh');painter.drawText(995,145,'Phạm vi đối chiếu và các phần điều chỉnh')
    painter.drawImage(35,165,draw([route_layer,reference,inside,hanoi],hanoi.extent(),895,820))
    painter.drawImage(970,165,draw([reference,added,removed,inside,hanoi],reference.extent(),895,820))
    painter.setFont(QFont('Arial',12));painter.setPen(QColor('#293848'))
    def key(x,y,color,text):
        painter.fillRect(x,y-14,25,15,QColor(color));painter.drawText(x+37,y,text)
    key(65,1030,'#176ea5','20 tuyến trong phạm vi lấy mẫu')
    key(65,1060,'#178560','40 tuyến ngoài phạm vi lấy mẫu')
    key(650,1030,'#fac57f','Phần thêm vào nhóm trong')
    key(650,1060,'#dbc5e0','Phần chuyển sang nhóm ngoài')
    key(1230,1030,'#c8e4ef','Phạm vi lấy mẫu trong sau điều chỉnh')
    painter.drawText(1230,1060,'Nét đứt tím: đường bao đối chiếu LEZ 2030')
    painter.setFont(QFont('Arial',12,QFont.Weight.Bold));painter.drawText(55,1120,'Ranh giới đối chiếu là hợp 36 địa bàn OSM theo Nghị quyết 57/2025; chưa xác minh độc lập GIS pháp lý.')
    painter.setFont(QFont('Arial',11));painter.drawText(55,1150,'17 phần sát ranh giới đổi nhóm; chỉ điều chỉnh trong dải 1 km. Chấm điểm: 50% mật độ dân cư + 50% mật độ cơ sở hoạt động OSM.')
    painter.drawText(55,1180,f"Tuyến là ứng viên tính bằng máy; điểm dừng, quyền lưu thông và tính đại diện còn cần kiểm tra. CRS: EPSG:3405. D (RC1–RC4): {report['candidates']['D_combined']:.4f}.")
    painter.drawText(55,1210,'Nguồn: OpenStreetMap contributors (ODbL), WorldPop API v2, Nghị quyết 57/2025/NQ-HĐND. Phạm vi nghiên cứu được lưu riêng với lớp đối chiếu.')
    painter.end()
    destination=work/'reports/sampling/LEZ2030_sampling_map.png';destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_name('.'+destination.name+'.tmp.png')
    if not canvas.save(str(temporary),'PNG'):raise RuntimeError('Map export failed')
    temporary.replace(destination)
    atomic_json(destination.with_suffix('.manifest.json'),{'created_at':now(),'zones_sha256':file_hash(zones),
                'routes_sha256':file_hash(routes),'map_sha256':file_hash(destination),'path':relative(destination,work)})
    return destination
