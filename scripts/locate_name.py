# -*- coding: utf-8 -*-
"""
locate_name.py - 自动逐页 OCR 定位姓名（可选学号双匹配）所在页码。

用法:
  python locate_name.py <pdf_dir> --name 张三 [--id 20260001] [--out result.json] [--zoom 2.0]

行为:
  - 遍历 pdf_dir 下所有 *.pdf（或 --files 指定多个文件）
  - 逐页渲染 + OCR 搜索姓名；配置 --id 时校验同一垂直带内出现学号，防同名误框
  - 全部页面未命中时自动升级 zoom: 2.0 -> 2.5 -> 3.0 -> 3.5 整页重试
  - 输出 result.json: {"文件.pdf": {"name_page": N, "box": [x0,y0,x1,y1], "hit_text": "..."}}
  - 未找到的文件单独列出（控制台+JSON 的 "not_found" 字段），供用户确认排除

隐私说明:
  - 控制台日志学号脱敏
  - 不产生任何残留文件（渲染在内存中完成）
"""
import json, sys, os, re, argparse
import fitz
import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR


def mask_id(text):
    return re.sub(r'(\d{4})\d+', r'\1***', text)


def _v_overlap(a, b, tol=12):
    return not (a[1] + tol < b[0] or b[1] + tol < a[0])


def render_page(pdf_path, page_num, zoom):
    doc = fitz.open(pdf_path)
    pix = doc[page_num - 1].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return img


def find_person(ocr_engine, img, name, target_id=None):
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


def locate_in_pdf(ocr, pdf_path, name, target_id, zooms):
    doc = fitz.open(pdf_path)
    n_pages = doc.page_count
    doc.close()
    last_err = None
    for zoom in zooms:
        for page in range(1, n_pages + 1):
            try:
                img = render_page(pdf_path, page, zoom)
                hit = find_person(ocr, img, name, target_id)
            except Exception as e:
                last_err = str(e)
                continue
            if hit:
                return {"name_page": page, "box": list(hit[0]),
                        "hit_text": hit[1], "zoom": zoom}
    if last_err:
        return {"error": last_err}
    return None


def main():
    ap = argparse.ArgumentParser(description="自动定位姓名所在页码")
    ap.add_argument("pdf_dir", help="PDF 所在目录")
    ap.add_argument("--name", required=True, help="要查找的姓名")
    ap.add_argument("--id", default=None, help="学号(可选，双条件匹配防同名)")
    ap.add_argument("--files", nargs="*", default=None, help="指定文件列表(默认目录下全部PDF)")
    ap.add_argument("--out", default=None, help="输出JSON路径")
    ap.add_argument("--zoom", type=float, default=2.0, help="起始zoom(默认2.0)")
    args = ap.parse_args()

    zooms = [args.zoom, 2.5, 3.0, 3.5]
    if args.files:
        pdfs = [os.path.join(args.pdf_dir, f) for f in args.files]
    else:
        pdfs = [os.path.join(args.pdf_dir, f) for f in sorted(os.listdir(args.pdf_dir))
                if f.lower().endswith(".pdf")]

    ocr = RapidOCR()
    results, not_found = {}, []
    for pdf in pdfs:
        fname = os.path.basename(pdf)
        hit = locate_in_pdf(ocr, pdf, args.name, args.id, zooms)
        if hit and "name_page" in hit:
            results[fname] = hit
            print(f"[命中] {fname}: 第{hit['name_page']}页 (zoom={hit['zoom']}) "
                  f"box={tuple(int(v) for v in hit['box'])} text={mask_id(hit['hit_text'])}")
        elif hit and "error" in hit:
            print(f"[错误] {fname}: {hit['error']}")
            not_found.append(fname)
        else:
            print(f"[未找到] {fname}")
            not_found.append(fname)

    if args.id:
        print(f"\n姓名: {args.name} 学号: {mask_id(args.id)} (双条件匹配)")
    summary = {"target_name": args.name, "target_id": args.id,
               "results": results, "not_found": not_found}
    print(f"\n共 {len(pdfs)} 份，命中 {len(results)} 份，未找到 {len(not_found)} 份")
    if not_found:
        print("未找到清单(请确认是否排除):")
        for f in not_found:
            print(f"  - {f}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"\n结果已写入: {args.out}")


if __name__ == "__main__":
    main()
