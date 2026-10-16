
const FIELDS = [
  ["province","Область"],["city","Город"],["district","Район"],["living_area","Жилмассив"],
  ["street_type","Тип улицы"],["street_name","Улица"],["house","Дом"],["apartment","Кв."],
  ["entrance","Подъезд"],["floor","Этаж"],["landmark","Ориентир"]
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
