from pathlib import Path
import json
from app.normalization import FIELD_WORDS, STREET_WORDS, TYPO_ALIASES
root = Path(__file__).resolve().parent
source = root / 'app' / 'static'
html = (source / 'page.html').read_text(encoding='utf-8-sig')
html = html.replace('/*STYLES*/', (source / 'styles.css').read_text(encoding='utf-8-sig'))
errors = json.loads((source / 'errors-log.json').read_text(encoding='utf-8-sig'))
html = html.replace('/*ERRORS*/', json.dumps(errors, ensure_ascii=False).replace('<', chr(92) + 'u003c'))
script = chr(10).join((source / name).read_text(encoding='utf-8-sig') for name in ('i18n.js', 'base.js', 'app.js', 'quality.js', 'account.js'))
lexicon=json.dumps({'fields':FIELD_WORDS,'streets':STREET_WORDS,'typos':TYPO_ALIASES},ensure_ascii=False,sort_keys=True).replace('<',chr(92)+'u003c')
script='const ADDRESS_LEXICON='+lexicon+';'+chr(10)+script
html = html.replace('/*SCRIPT*/', script)
(source / 'index.html').write_text(html, encoding='utf-8')
print('Built app/static/index.html')
