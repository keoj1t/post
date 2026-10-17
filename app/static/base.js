
const FIELDS = [
  ["province","Область"],["city","Город"],["district","Район"],["living_area","Жилмассив"],
  ["street_type","Тип улицы"],["street_name","Улица"],["house","Дом"],["apartment","Кв."],
  ["entrance","Подъезд"],["floor","Этаж"],["landmark","Ориентир"],["postal_code","Индекс"],["building","Корпус"],["structure","Строение"]
];
// сокращения, которыми тип улицы может быть записан в исходной строке
const ABBR = {
  "улица":["улица","ул.","ул"], "проспект":["проспект","пр-т","пр.","пр"], "переулок":["переулок","пер.","пер"],
  "бульвар":["бульвар","бул.","бул"], "микрорайон":["микрорайон","мкр.","мкр"], "площадь":["площадь","пл.","пл"],
  "шоссе":["шоссе","ш."], "тупик":["тупик"], "набережная":["набережная","наб."]
};
let rows = [];

const $ = id => document.getElementById(id);
const status = (t, err) => { const s=$("status"); s.textContent=translateText(t); s.className = err ? "err" : ""; };



// Те же варианты пропущенной буквы, что поддерживает парсер.
for(const marker of ['переулок','проспект','микрорайон','бульвар']){
  if(!ABBR[marker])ABBR[marker]=[marker];
  for(let i=0;i<marker.length;i++)ABBR[marker].push(marker.slice(0,i)+marker.slice(i+1));
}

ABBR['улица'].push('көше','көшесі','көш','street','st','ul');
ABBR['проспект'].push('даңғыл','даңғылы','avenue','ave');
ABBR['переулок'].push('тұйық','тұйығы','lane');
ABBR['микрорайон'].push('шағынаудан','ықшамаудан');

ABBR['проезд']=['проезд','өтпе','өткел'];ABBR['площадь']=['площадь','пл','алаң','алаңы'];ABBR['набережная']=['набережная','наб','жағалау','жағалауы'];
// Подсветка использует тот же словарь, что и серверный парсер.
for(const [kind,words] of Object.entries(ADDRESS_LEXICON.streets)){
  const typos=Object.entries(ADDRESS_LEXICON.typos).filter(([,target])=>words.includes(target)).map(([alias])=>alias);
  ABBR[kind]=[...new Set([...(ABBR[kind]||[]),...words,...typos])];
}
function numericMarkerPattern(field){
  const words=ADDRESS_LEXICON.fields[field]||[];
  const typos=Object.entries(ADDRESS_LEXICON.typos).filter(([,target])=>words.includes(target)).map(([alias])=>alias);
  return [...new Set([...words,...typos])].sort((a,b)=>b.length-a.length).map(word=>word.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|');
}
