from pathlib import Path
import mistune
from weasyprint import HTML,CSS
from bs4 import BeautifulSoup
P=Path(__file__).parent
md=P.joinpath('PULSE_BLUEPRINT.md').read_text()
markdown=mistune.create_markdown(escape=False, plugins=['table','strikethrough','url'])
html=markdown(md)
# fix html escaping for valid image captions and manual divs
page='''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>PULSE Engineering Blueprint</title></head><body>'''+html+'''</body></html>'''
(P/'preview.html').write_text(page)
HTML(string=page,base_url=str(P)).write_pdf('/mnt/data/PULSE_Software_Engineering_Blueprint_v0.1.pdf',stylesheets=[CSS(filename=str(P/'style.css'))],presentational_hints=True)
print('pdf rendered')
