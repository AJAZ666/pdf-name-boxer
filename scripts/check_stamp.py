# -*- coding: utf-8 -*-
"""
check_stamp.py - 检测 PDF 页面是否含公章（红色印章像素）。

用法:
  python check_stamp.py <pdf文件> --page 1 [--pages 1,3,5] [--zoom 1.0] [--threshold 0.0003]

判定逻辑:
  - 渲染页面，统计"红色像素"(R>120 且 R-G>40 且 R-B>40)占整页比例
  - 占比 >= threshold 判定"检测到公章痕迹"，否则"未检测到"
  - 阈值默认 0.0003（约万分之三），公章通常占 0.1%-2%，正常文字不会误报

用途:
  - 生成证明Word前跑一遍，确认截取的说明页是否真的包含公章
  - 若原文件本身无章(如学校电子证明模板)，提前告知用户，避免静默交付
"""
import sys, os, argparse
import fitz
import numpy as np
from PIL import Image


def render_page(pdf_path, page_num, zoom):
    doc = fitz.open(pdf_path)
    pix = doc[page_num - 1].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return img


def stamp_ratio(img):
    arr = np.asarray(img).astype(int)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    mask = (r > 120) & ((r - g) > 40) & ((r - b) > 40)
    return float(mask.sum()) / mask.size


def main():
    ap = argparse.ArgumentParser(description="检测PDF页面是否含公章")
    ap.add_argument("pdf", help="PDF 文件路径")
    ap.add_argument("--page", type=int, default=None, help="检测单页")
    ap.add_argument("--pages", default=None, help="检测多页，逗号分隔，如 1,2,3")
    ap.add_argument("--zoom", type=float, default=1.0, help="渲染zoom(默认1.0，足够检测颜色)")
    ap.add_argument("--threshold", type=float, default=0.0003, help="红色像素占比阈值")
    args = ap.parse_args()

    if not os.path.exists(args.pdf):
        print(f"文件不存在: {args.pdf}")
        sys.exit(1)

    pages = []
    if args.pages:
        pages = [int(p) for p in args.pages.split(",")]
    elif args.page:
        pages = [args.page]
    else:
        doc = fitz.open(args.pdf)
        pages = list(range(1, doc.page_count + 1))
        doc.close()

    fname = os.path.basename(args.pdf)
    any_stamp = False
    for p in pages:
        try:
            img = render_page(args.pdf, p, args.zoom)
            ratio = stamp_ratio(img)
        except Exception as e:
            print(f"p{p}: 渲染失败 {e}")
            continue
        flag = "检测到公章" if ratio >= args.threshold else "未检测到公章"
        if ratio >= args.threshold:
            any_stamp = True
        print(f"{fname} p{p}: {flag}（红色像素占比 {ratio*100:.3f}%）")

    if not any_stamp:
        print("\n提示: 全部页面未检测到公章痕迹。若为学校电子证明模板请忽略；"
              "若纸质扫描件应有章，请人工确认扫描质量。")


if __name__ == "__main__":
    main()
