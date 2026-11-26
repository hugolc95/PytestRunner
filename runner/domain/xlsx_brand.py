"""Identite IN Groupe embarquee dans le XLSX, sans image ni police distante."""
from importlib.resources import files

BLUE = '002F87'
RED = 'EA0029'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def brand_content_types(sheet_count):
    return ('<Default Extension="png" ContentType="image/png"/>'
            '<Override PartName="/xl/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
            + ''.join(f'<Override PartName="/xl/drawings/drawing{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>'
                      for i in range(1, sheet_count + 1)))


def write_brand(book, sheet_count):
    book.writestr('xl/media/in-groupe.png', files('runner.report_assets').joinpath('in-groupe.png').read_bytes())
    colors = dict(dk1='1B2230', lt1='FFFFFF', dk2=BLUE, lt2='EFF3FA', accent1=BLUE,
                  accent2=RED, accent3='007A78', accent4='7155A6', accent5='B57F14',
                  accent6='63748A', hlink=BLUE, folHlink='6B478B')
    color_scheme = ''.join(f'<a:{name}><a:srgbClr val="{value}"/></a:{name}>' for name, value in colors.items())
    fonts = ''.join(f'<a:{name}><a:latin typeface="{typeface}"/><a:ea typeface=""/><a:cs typeface=""/></a:{name}>'
                    for name, typeface in (('majorFont', 'Aptos Display'), ('minorFont', 'Aptos')))
    fill = '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    lines = ''.join(f'<a:ln w="{width}" cap="flat" cmpd="sng" algn="ctr">{fill}<a:prstDash val="solid"/><a:miter lim="800000"/></a:ln>'
                    for width in (9525, 25400, 38100))
    theme = ('<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="IN Groupe">'
             f'<a:themeElements><a:clrScheme name="IN Groupe">{color_scheme}</a:clrScheme>'
             f'<a:fontScheme name="IN Groupe">{fonts}</a:fontScheme>'
             f'<a:fmtScheme name="IN Groupe"><a:fillStyleLst>{fill * 3}</a:fillStyleLst>'
             f'<a:lnStyleLst>{lines}</a:lnStyleLst><a:effectStyleLst>'
             + '<a:effectStyle><a:effectLst/></a:effectStyle>' * 3
             + f'</a:effectStyleLst><a:bgFillStyleLst>{fill * 3}</a:bgFillStyleLst>'
             '</a:fmtScheme></a:themeElements></a:theme>')
    book.writestr('xl/theme/theme1.xml', theme)
    # Ancrage dans la premiere ligne, toujours visible et hors du plan de
    # regroupement. Un seul PNG partage par les trois feuilles.
    drawing = f'''<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="{REL}">
<xdr:oneCellAnchor><xdr:from><xdr:col>0</xdr:col><xdr:colOff>114300</xdr:colOff><xdr:row>0</xdr:row><xdr:rowOff>76200</xdr:rowOff></xdr:from><xdr:ext cx="1047750" cy="631145"/>
<xdr:pic><xdr:nvPicPr><xdr:cNvPr id="1" name="IN Groupe" descr="IN Groupe logo"/><xdr:cNvPicPr><a:picLocks noChangeAspect="1"/></xdr:cNvPicPr></xdr:nvPicPr><xdr:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill><xdr:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr></xdr:pic><xdr:clientData/></xdr:oneCellAnchor></xdr:wsDr>'''
    for identifier in range(1, sheet_count + 1):
        book.writestr(f'xl/drawings/drawing{identifier}.xml', drawing)
        book.writestr(f'xl/drawings/_rels/drawing{identifier}.xml.rels',
            f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{REL}/image" Target="../media/in-groupe.png"/></Relationships>')
        book.writestr(f'xl/worksheets/_rels/sheet{identifier}.xml.rels',
            f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{REL}/drawing" Target="../drawings/drawing{identifier}.xml"/></Relationships>')
