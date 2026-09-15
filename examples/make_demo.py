# -*- coding: utf-8 -*-
"""
make_demo.py - 生成完全虚构的演示材料（可选）：
  examples/sample_proof.pdf   虚构活动证明（假学校/假活动/假姓名/假学号）
  examples/demo_result.png    真实运行效果图（说明+表头+红框名字）

所有内容均为虚构，不含任何真实个人信息。
依赖: pymupdf pillow rapidocr-onnxruntime numpy （见 README 快速开始）
"""
import os, json
import fitz
import numpy as np
from PIL import Image, ImageDraw
from rapidocr_onnxruntime import RapidOCR

HERE = os.path.dirname(os.path.abspath(__file__))
EX = os.path.join(HERE, "examples")
os.makedirs(EX, exist_ok=True)
PDF = os.path.join(EX, "sample_proof.pdf")


def put(page, text, x, y, size=11, center_w=None):
    if center_w:
        tw = fitz.get_text_length(text, fontname="china-s", fontsize=size)
        x = (center_w - tw) / 2
    page.insert_text((x, y), text, fontsize=size, fontname="china-s")


# ---------- 1. 生成虚构示例 PDF ----------
doc = fitz.open()
page = doc.new_page(width=595, height=842)
put(page, "某高校就业指导专题讲座活动综测证明", 0, 90, size=16, center_w=595)
put(page, "（示例文件 · 内容均为虚构）", 0, 115, size=10, center_w=595)
body = [
    "兹证实，以下同学于2026年3月1日(周日)参加由某高校举",
    "办的2026年就业指导专题讲座，按照《某高校综合测评条例》，可在智育板",
    "块进行综测加分。情况属实，特此证明。",
]
y = 165
for line in body:
    put(page, line, 80, y)
    y += 22
put(page, "某高校", 380, 320)
put(page, "2026年3月2日", 400, 345)
put(page, "参与人员名单如下", 80, 400)
put(page, "学号", 130, 435)
put(page, "姓名", 330, 435)
rows = [
    ("20250001", "王小明"), ("20250002", "李小红"), ("20250003", "赵大勇"),
    ("20260001", "张三"),   ("20260002", "李四"),   ("20260003", "王五"),
    ("20260004", "赵六"),   ("20260005", "孙七"),
]
y = 465
for sid, nm in rows:
    put(page, sid, 130, y)
    put(page, nm, 330, y)
    y += 30
doc.save(PDF)
doc.close()
print(f"示例PDF已生成: {PDF}")

# ---------- 2. 生成真实运行效果图（红框框住"张三"） ----------
ocr = RapidOCR()


def render_page(pdf_path, page_num, zoom):
    d = fitz.open(pdf_path)
    pix = d[page_num - 1].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    d.close()
    return img


def find_text(engine, img, kw):
    res, _ = engine(np.array(img))
    for line in (res or []):
        box, text, _ = line
        if kw in text:
            return (min(p[0] for p in box), min(p[1] for p in box),
                    max(p[0] for p in box), max(p[1] for p in box)), text
    return None, None


def merge_vertical(images, gap=20):
    max_w = max(im.width for im in images)
    total_h = sum(im.height for im in images) + gap * (len(images) - 1)
    canvas = Image.new("RGB", (max_w, total_h), "white")
    y = 0
    for im in images:
        canvas.paste(im, ((max_w - im.width) // 2, y))
        y += im.height + gap
    return canvas


zoom, pad = 2.0, 12
full = render_page(PDF, 1, zoom)
hbox, _ = find_text(ocr, full, "姓名")
h_bottom = int(hbox[3] + 15) if hbox else int(full.height * 0.5)
header_img = full.crop((int(full.width * 0.06), int(full.height * 0.05),
                        int(full.width * 0.94), h_bottom))
nbox, _ = find_text(ocr, full, "张三")
if nbox:
    cy = (nbox[1] + nbox[3]) / 2
    half_h = 120
    cy0 = max(0, int(cy - half_h))
    cy1 = min(full.height, int(cy + half_h))
    c_l, c_r = int(full.width * 0.05), int(full.width * 0.95)
    name_img = full.crop((c_l, cy0, c_r, cy1))
    draw = ImageDraw.Draw(name_img)
    draw.rectangle((nbox[0] - c_l - pad, nbox[1] - cy0 - pad,
                    nbox[2] - c_l + pad, nbox[3] - cy0 + pad),
                   outline=(255, 0, 0), width=5)
else:
    raise RuntimeError("示例PDF中未找到张三，请检查PyMuPDF内置CJK字体是否可用")
out_png = os.path.join(EX, "demo_result.png")
merge_vertical([header_img, name_img]).save(out_png)
print(f"效果图已生成: {out_png}")

# ---------- 3. 生成示例配置模板 ----------
cfg = {
    "pdf_dir": "examples",
    "output": "output/综测证明_整理结果.docx",
    "target_name": "张三",
    "target_id": "20260001",
    "zoom": 2.0,
    "box_pad": 12,
    "tasks": [
        {
            "file": "sample_proof.pdf",
            "title": "1. 某高校就业指导专题讲座，+1（智育1）",
            "name_page": 1,
            "header_page": 1,
            "half_height": 300
        }
    ]
}
cfg_path = os.path.join(EX, "config.example.json")
with open(cfg_path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
print(f"示例配置已生成: {cfg_path}")
print("\n全部为虚构数据。正式使用时，把真实材料替换进来即可。")
