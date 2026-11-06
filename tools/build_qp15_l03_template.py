"""Build static/templates/QP15-L03.docx from the lab's own SMH-LAB-QP15 Word file.

Keeps only 附件6 (QP15-L03 人員能力評估考核紀錄表) with the SOP's own header/footer,
then turns the blanks into docxtemplater tags:
  {#exams} ... {/exams}   one page per exam (考卷)
  {title} {item} {trainingDate} {examDate}
  {#rows}{name}{evaluator}{date}{yes}{no}{validUntil}{note}{/rows}
Usage: python tools/build_qp15_l03_template.py QP15.docx static/templates/QP15-L03.docx
"""
import copy, sys
import docx
from docx.oxml.ns import qn


def text_of(el):
    return ''.join(t.text or '' for t in el.iter(qn('w:t')))


def set_para(p, text):
    runs = p.findall(qn('w:r'))
    keep = runs[0] if runs else None
    for r in runs[1:]:
        p.remove(r)
    if keep is None:
        keep = p.makeelement(qn('w:r'), {}); p.append(keep)
    for child in list(keep):
        if child.tag != qn('w:rPr'):
            keep.remove(child)
    t = keep.makeelement(qn('w:t'), {}); t.text = text
    t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    keep.append(t)


def set_cell(tc, text):
    ps = tc.findall(qn('w:p'))
    for p in ps[1:]:
        tc.remove(p)
    set_para(ps[0], text)


def main(src, dst):
    d = docx.Document(src)
    body = d.element.body
    els = list(body)
    start = next(i for i, e in enumerate(els) if text_of(e).strip().startswith('附件6'))
    end = next(i for i, e in enumerate(els) if i > start and '附件7' in text_of(e))
    # sectPr of the section that holds 附件6 (first sectPr at/after `end`).
    sect = None
    for e in els[end:]:
        s = e.find('.//' + qn('w:sectPr')) if e.tag != qn('w:sectPr') else e
        if s is not None:
            sect = copy.deepcopy(s); break
    # Sections inherit the page header/footer from the first section; copy its
    # default header/footer references so the sheet keeps the SOP running header.
    first_sect = next(e.find('.//' + qn('w:sectPr')) for e in els if e.find('.//' + qn('w:sectPr')) is not None)
    refs = [copy.deepcopy(r) for r in first_sect
            if r.tag in (qn('w:headerReference'), qn('w:footerReference')) and r.get(qn('w:type')) == 'default']
    if sect is not None and not sect.findall(qn('w:headerReference')):
        for i, r in enumerate(refs):
            sect.insert(i, r)
    keep = els[start:end + 1]
    for e in els:
        if e not in keep:
            body.remove(e)
    title_p, item_p, date_p = [e for e in keep if e.tag == qn('w:p') and text_of(e).strip()][2:5]
    set_para(title_p, '名稱：{title}')
    set_para(item_p, '評估項目：{item}')
    set_para(date_p, '教育訓練日期：{trainingDate}　　　　考核日期：{examDate}')
    last = keep[-1]
    set_para(last, '（應定期接受考核）')
    for br in last.findall('.//' + qn('w:br')):
        br.getparent().remove(br)
    tbl = next(e for e in keep if e.tag == qn('w:tbl'))
    rows = tbl.findall(qn('w:tr'))
    for r in rows[2:]:
        tbl.remove(r)
    cells = rows[1].findall(qn('w:tc'))
    vals = ['{#rows}{name}', '{evaluator}', '{date}', '{yes}是{no}否', '{validUntil}', '{note}{/rows}']
    for tc, v in zip(cells, vals):
        set_cell(tc, v)
    # each exam starts on a new page
    first = keep[0]
    ppr = first.find(qn('w:pPr'))
    if ppr is None:
        ppr = first.makeelement(qn('w:pPr'), {}); first.insert(0, ppr)
    ppr.insert(0, ppr.makeelement(qn('w:pageBreakBefore'), {}))
    open_p = copy.deepcopy(title_p); set_para(open_p, '{#exams}')
    close_p = copy.deepcopy(title_p); set_para(close_p, '{/exams}')
    body.insert(0, open_p)
    body.append(close_p)
    for s in body.findall('.//' + qn('w:sectPr')):
        s.getparent().remove(s)
    body.append(sect)
    d.save(dst)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
