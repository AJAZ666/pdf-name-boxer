# -*- coding: utf-8 -*-
"""
PDF Name Boxer v2 - 从PDF中自动定位指定姓名(可选学号双匹配)，画红框，截取说明+名字区域，生成Word。

用法:
  python box_names.py config.json

config.json 格式:
{
  "pdf_dir": "PDF所在目录",
  "output": "输出Word路径",
  "target_name": "要框出的姓名",
  "target_id": "学号(可选，防止同名误框)",
  "zoom": 2.0,
  "box_pad": 12,
  "tasks": [
    {
      "file": "证明1.pdf",
      "title": "1. 活动名称",
      "name_page": 1,
      "header_page": 1,
      "half_height": 350,
      "single_page": false
    }
  ]
}
  - half_height: 以名字为中心上下各取多少像素；设为null则single_page=true（只截一张全宽图）
  - single_page: true时只截一页（说明和名字紧挨着的情况）
  - target_id: 可选；配置后同名匹配会校验学号，避免框错同名者

隐私说明:
  - 临时截图保存在输出目录，运行结束自动删除（含异常中断兜底清理）
  - 控制台日志不打印完整学号
"""
import json, sys, os, re
import fitz
import numpy as np
from PIL import Image, ImageDraw
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from rapidocr_onnxruntime import RapidOCR


def mask_id(text):
    """日志脱敏：4位以上数字串只保留前4位"""
    return re.sub(r'(\d{4})\d+', r'\1***', text)


def render_page(pdf_path, page_num, zoom):
    doc = fitz.open(pdf_path)
    pix = doc[page_num - 1].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return img


def _v_overlap(a, b, tol=12):
    """两行文字的垂直范围是否重叠（允许tol像素容差）"""
    return not (a[1] + tol < b[0] or b[1] + tol < a[0])


def find_person(ocr_engine, img, name, target_id=None):
    """
    查找姓名（可选学号双条件匹配）。
    返回 (box, hit_text) 或 None。
    - 配置了target_id: 找到姓名且同垂直带内出现学号才算命中；有姓名但学号不匹配返回None(疑似同名)
    - 未配置target_id: 返回第一个含姓名的文本行
    """
    result, _ = ocr_engine(np.array(img))
    lines = []
    for line in (result or []):
        box, text, _ = line
        lines.append((min(p[0] for p in box), min(p[1] for p in box),
                      max(p[0] for p in box), max(p[1] for p in box), text))
    cands = [ln for ln in lines if name in ln[4]]
    if not cands:
        return None
    if target_id:
        for c in cands:
            for ln in lines:
                if target_id in ln[4] and _v_overlap((c[1], c[3]), (ln[1], ln[3])):
                    return (c[0], c[1], c[2], c[3]), ln[4]
        return None
    return (cands[0][0], cands[0][1], cands[0][2], cands[0][3]), cands[0][4]


def merge_vertical(images, gap=20):
    max_w = max(im.width for im in images)
    total_h = sum(im.height for im in images) + gap * (len(images) - 1)
    canvas = Image.new("RGB", (max_w, total_h), "white")
    y = 0
    for im in images:
        canvas.paste(im, ((max_w - im.width) // 2, y))
        y += im.height + gap
    return canvas


def main():
    with open(sys.argv[1], encoding="utf-8") as f:
        cfg = json.load(f)

    ocr = RapidOCR()
    zoom = cfg.get("zoom", 2.0)
    pad = cfg.get("box_pad", 12)
    target = cfg["target_name"]
    target_id = cfg.get("target_id")
    if target_id:
        print(f"目标: {target} (学号 {mask_id(target_id)}，双条件匹配)")
    else:
        print(f"目标: {target} (未配置学号，建议补充 target_id 防同名误框)")
    red = (255, 0, 0)
    box_w = 5

    doc = Document()
    doc.styles['Normal'].font.name = '宋体'
    doc.styles['Normal'].font.size = Pt(11)

    tmp_files = []
    out_dir = os.path.dirname(cfg["output"])
    os.makedirs(out_dir, exist_ok=True)

    try:
        for task in cfg["tasks"]:
            fname = task["file"]
            title = task["title"]
            name_page = task["name_page"]
            head_page = task.get("header_page", name_page)
            half_h = task.get("half_height")
            single = task.get("single_page", half_h is None)

            pdf_path = os.path.join(cfg["pdf_dir"], fname)
            print(f"Processing: {fname}")
            doc.add_heading(title, level=2)

            if single:
                img = render_page(pdf_path, name_page, zoom)
                hit = find_person(ocr, img, target, target_id)
                if hit:
                    box, hit_text = hit
                    draw = ImageDraw.Draw(img)
                    draw.rectangle((box[0]-pad, box[1]-pad, box[2]+pad, box[3]+pad),
                                   outline=red, width=box_w)
                else:
                    print(f"  [警告] 第{name_page}页未找到 {target}"
                          f"{'且学号匹配' if target_id else ''}，本项无红框！")
                tmp = os.path.join(out_dir, f"_tmp_{abs(hash(fname))}.png")
                img.save(tmp)
                tmp_files.append(tmp)
                doc.add_picture(tmp, width=Inches(5.5))
            else:
                # header crop: 截到"姓名"表头文字下方(保留表头行)
                head_full = render_page(pdf_path, head_page, zoom)
                header_xy = find_person(ocr, head_full, "姓名")
                if header_xy:
                    h_bottom = int(header_xy[0][3] + 15)
                else:
                    h_bottom = int(head_full.height * 0.5)
                h_top = int(head_full.height * 0.05)
                h_l = int(head_full.width * 0.06)
                h_r = int(head_full.width * 0.94)
                header_img = head_full.crop((h_l, h_top, h_r, h_bottom))

                # name crop
                name_full = render_page(pdf_path, name_page, zoom)
                hit = find_person(ocr, name_full, target, target_id)
                if not hit:
                    raise RuntimeError(
                        f"OCR未在 {fname} 第{name_page}页找到 '{target}'"
                        f"{'且学号匹配' if target_id else ''}。"
                        f"建议: 提高zoom / 用 locate_name.py 复核页码 / 确认学号配置")
                box, _ = hit

                cy = (box[1] + box[3]) / 2
                cy0 = max(0, int(cy - half_h))
                cy1 = min(name_full.height, int(cy + half_h))
                if cy0 == 0 and cy1 < cy + half_h:  # 顶部截断时向下补偿
                    cy1 = min(name_full.height, int(cy + half_h) + int(half_h - cy))
                c_l = int(name_full.width * 0.05)
                c_r = int(name_full.width * 0.95)
                name_img = name_full.crop((c_l, cy0, c_r, cy1))

                draw = ImageDraw.Draw(name_img)
                draw.rectangle((box[0]-c_l-pad, box[1]-cy0-pad,
                                box[2]-c_l+pad, box[3]-cy0+pad),
                               outline=red, width=box_w)

                merged = merge_vertical([header_img, name_img])
                tmp = os.path.join(out_dir, f"_tmp_{abs(hash(fname))}.png")
                merged.save(tmp)
                tmp_files.append(tmp)
                doc.add_picture(tmp, width=Inches(5.5))

            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            doc.add_paragraph()

        doc.save(cfg["output"])
        print(f"\nDone: {cfg['output']}")
    finally:
        # 兜底清理临时截图（含异常中断），避免私人信息残留
        for t in tmp_files:
            try:
                if os.path.exists(t):
                    os.remove(t)
            except Exception:
                pass


if __name__ == "__main__":
    main()
