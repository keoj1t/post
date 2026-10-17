// Состояние интерфейса отделено от оригинального ответа API.
const create=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
const examples=['66квартал 12дом 69квартира','Ул .Курильская 9 кв 1','Туран 55/6 магазин береке 4подьезд 9этаж','Нурсити 2 микрорайон 11дом 5 подьезд 239 кв','город Алматы/Алматы қаласы, Мкр Аксай 3а, 59, кв 70'];
let original=[],reviewed=new Set(),disabledFields=new Set(),page=0,tokenIndex=0,queueIndex=0,activeTab='parse',threshold=.6,queueCurrentRow=null;
const confidence=r=>typeof r.confidence==='number'&&Number.isFinite(r.confidence)?r.confidence:0;
const clone=x=>JSON.parse(JSON.stringify(x));
function save(key,value){try{localStorage.setItem(key,value);}catch{}}
function load(key){try{return localStorage.getItem(key);}catch{return null;}}
let theme=load('jana-theme')||'light';
function applyTheme(){document.documentElement.dataset.theme=theme;$('theme').setAttribute('aria-pressed',String(theme==='dark'));}applyTheme();
$('theme').onclick=()=>{theme=theme==='dark'?'light':'dark';applyTheme();save('jana-theme',theme);};
const saved=load('jana-threshold');if(saved!==null&&Number.isFinite(+saved)&&+saved>=0&&+saved<=1)threshold=+saved;$('threshold').value=threshold;
function tab(name){
  activeTab=name;
  document.querySelectorAll('[role=tabpanel]').forEach(panel=>panel.hidden=panel.id!==name);
  document.querySelectorAll('[data-tab]').forEach(button=>button.setAttribute('aria-selected',String(button.dataset.tab===name)));
  const title=$('title'),subtitle=$('subtitle');title.textContent='';
  if(name==='parse'){
    title.append(document.createTextNode(language==='kk'?'Әр мекенжай.':'Каждый адрес.'),create('br'),create('span',language==='kk'?'Өз орнында.':'На своём месте.'));
    subtitle.textContent=language==='kk'?'Мекенжайларды қосыңыз — бәрін ретке келтіреміз. Сізге тек тексеріп, сақтау қалады.':'Добавьте адреса — мы разложим всё по полочкам. Вам останется проверить и сохранить.';
  }else{
    title.textContent=translateText(name==='tokens'?'Детали адреса':name==='errors'?'Ошибки и исправления':'Неуверенные сначала');
    subtitle.textContent=translateText(name==='tokens'?'Нажмите на поле, чтобы внести изменения.':name==='errors'?'Примеры, которые помогли улучшить распознавание.':'Проверьте выделенные адреса и при необходимости исправьте поля.');
  }
  document.querySelector('.hero-card').hidden=name!=='parse';document.querySelector('.hero-steps').hidden=name!=='parse';
  if(name==='tokens')renderTokens();if(name==='queue')renderQueue();if(name==='errors')renderErrors();
}
document.querySelectorAll('[data-tab]').forEach(e=>{e.onclick=()=>tab(e.dataset.tab);e.onkeydown=event=>{if(!['ArrowLeft','ArrowRight'].includes(event.key))return;event.preventDefault();const tabs=[...document.querySelectorAll('[data-tab]')];const next=tabs[(tabs.indexOf(e)+(event.key==='ArrowRight'?1:tabs.length-1))%tabs.length];next.focus();tab(next.dataset.tab);};});
// Карта позиций игнорирует невидимые символы, сохраняя raw_address побайтно в запросе.
function searchable(raw){
  let text='',map=[],previous='';
  for(let i=0;i<raw.length;i++){
    const current=raw[i];
    if(/[\u200b-\u200f\u2060\ufeff\u00ad]/.test(current))continue;
    // Виртуальный пробел связывает «Коктал1» с «Коктал 1», не меняя raw_address.
    if(previous&&((/\p{L}/u.test(previous)&&/\d/.test(current))||(/\d/.test(previous)&&/\p{L}/u.test(current)))){text+=' ';map.push(i);}
    text+=current.toLowerCase();map.push(i);previous=current;
  }
  return {text,map};
}
const word=c=>!!c&&/[\p{L}\p{N}_]/u.test(c),digit=c=>!!c&&/\d/.test(c);
function findRange(raw,value,used,field){if(value==null||String(value)==='')return null;const {text,map}=searchable(raw);const candidates=field==='street_type'?(ABBR[String(value).toLowerCase()]||[String(value)]):[String(value)];for(const candidate of candidates){const needle=searchable(candidate).text;let from=0;while(needle&&from<text.length){const i=text.indexOf(needle,from);if(i<0)break;const j=i+needle.length,left=!word(text[i-1])||digit(text[i-1])!==digit(text[i]),right=!word(text[j])||digit(text[j-1])!==digit(text[j]);const a=map[i],b=map[j-1]+1;if(left&&right&&!used.some(([x,y])=>a<y&&b>x))return [a,b];from=i+1;}}return null;}
// Подсвечиваем число вместе с маркером поля, включая слитное написание.
function ranges(row){
  const raw=String(row.raw_address??''),used=[],marks=[];
  const markers={living_area:'ж\\s*[./]?\\s*м[.]?|жилмассив|жилой\\s+массив|тұрғын\\s+алап',house:'дом|дм|д|үй|үйі|уй|bld|house',apartment:'квартира|кварт|кв|flat|kv|апт|пәтер|пәтері|apt|appt',entrance:'подъезд|подьезд|подьедз|подъедз|подезд|подъ|под|кіреберіс|кіреберісі|entrance',floor:'этаж|эт|floor|қабат|қабаты',postal_code:'индекс|индексі|postal code|zip',building:'корпус|корп|к|блок|block|корпусы',structure:'строение|стр|құрылыс|құрылысы'};
  Object.keys(ADDRESS_LEXICON.fields).forEach(key=>{markers[key]=numericMarkerPattern(key)||markers[key];});
  FIELDS.map(([k])=>k).sort((a,b)=>String(row[b]??'').length-String(row[a]??'').length||(a==='city'?-1:b==='city'?1:0)).forEach(k=>{
    const range=findRange(raw,row[k],used,k);if(!range)return;
    let [a,b]=range;
    if(markers[k]){
      const prefix=new RegExp('(?<![\\p{L}])(?:'+markers[k]+')[.\\s]*$','iu').exec(raw.slice(0,a));
      const suffix=new RegExp('^[.\\s]*(?:'+markers[k]+')(?![\\p{L}])','iu').exec(raw.slice(b));
      const x=prefix?prefix.index:a,y=!prefix&&suffix?b+suffix[0].length:b;
      if(!used.some(([u,v])=>x<v&&y>u)){a=x;b=y;}
    }
    used.push([a,b]);marks.push([a,b,k]);
  });
  return marks.sort((a,b)=>a[0]-b[0]);
}
function renderRaw(target,row){target.textContent='';const raw=String(row.raw_address??'');let position=0;for(const [a,b,key] of ranges(row)){target.append(document.createTextNode(raw.slice(position,a)));const mark=create(disabledFields.has(key)?'span':'mark',raw.slice(a,b));if(!disabledFields.has(key))mark.style.background=translateText(`var(--c-${key})`);mark.title=fieldLabel(row,key);target.append(mark);position=b;}target.append(document.createTextNode(raw.slice(position)));}
function renderLegends(){for(const id of ['legend','tokenLegend']){$(id).textContent='';FIELDS.forEach(([k,label])=>{const chip=create('button',translateText(label),'chip');chip.style.background=translateText(`var(--c-${k})`);chip.setAttribute('aria-pressed',String(!disabledFields.has(k)));chip.onclick=()=>{disabledFields.has(k)?disabledFields.delete(k):disabledFields.add(k);renderLegends();renderTable();renderTokens();renderQueue();};$(id).append(chip);});}}
function badge(row){const c=confidence(row);return create('span',translateText(`${Math.round(c*100)}%`),'badge '+(c>=.8?'good':c>=.6?'medium':'low'));}
function updateStats(){const n=rows.length;$('total').textContent=n;$('average').textContent=n?Math.round(rows.reduce((s,r)=>s+confidence(r),0)/n*100)+'%':'—';const low=rows.filter((row,index)=>needsReview(row)&&!reviewed.has(index)).length;$('uncertain').textContent=low;$('qcount').textContent=low;$('filled').textContent=n?Math.round(rows.reduce((s,r)=>s+FIELDS.filter(([k])=>r[k]!=null&&r[k]!=='').length,0)/(n*FIELDS.length)*100)+'%':'—';$('coverage').textContent='';FIELDS.forEach(([k,label])=>{$('coverage').append(create('span',translateText(`${label}: ${n?Math.round(rows.filter(r=>r[k]!=null&&r[k]!=='').length/n*100):0}%`)));});$('thresholdValue').textContent=threshold.toFixed(2);['dlJson','dlCsv','copy','undo','queueJson','queueCsv'].forEach(id=>$(id).disabled=!n);updateValidationSummary();}
function filteredRows(){let list=rows.map((row,index)=>({row,index}));const query=$('search').value.toLocaleLowerCase();if(query)list=list.filter(({row})=>Object.values(row).some(v=>String(v??'').toLocaleLowerCase().includes(query)));if($('onlylow').checked)list=list.filter(({row})=>needsReview(row));if($('sort').value!=='original')list.sort((a,b)=>(confidence(a.row)-confidence(b.row))*($('sort').value==='asc'?1:-1));return list;}
function revert(index){rows[index]=clone(original[index]);reviewed.delete(index);refresh();}
function renderTable(){const list=filteredRows(),pages=Math.max(1,Math.ceil(list.length/50));page=Math.min(page,pages-1);$('tbody').textContent='';if(!list.length){const tr=create('tr'),td=create('td');td.colSpan=FIELDS.length+3;td.className='empty';td.textContent=rows.length?translateText('Совпадений не найдено'):translateText('Добавьте адреса, чтобы увидеть результат.');tr.append(td);$('tbody').append(tr);}for(const {row,index} of list.slice(page*50,page*50+50)){const tr=create('tr'),number=create('td',index+1),undo=create('button','↶');undo.title=translateText('Отменить изменения');undo.setAttribute('aria-label','Откатить строку '+(index+1));undo.onclick=()=>revert(index);number.append(undo);tr.append(number);const raw=create('td',undefined,'raw');renderRaw(raw,row);if(reviewed.has(index))raw.append(create('div',translateText('✓ Проверено человеком'),'tag'));tr.append(raw);FIELDS.forEach(([k,label])=>{const td=create('td',row[k]??'','f');td.contentEditable='plaintext-only';td.setAttribute('aria-label',`${translateText(label)}, ${index+1}`);td.style.background=row[k]?translateText(`var(--c-${k})`):'';td.classList.toggle('edited',row[k]!==original[index][k]);td.oninput=()=>{row[k]=td.textContent.trim()||null;reviewed.delete(index);td.classList.toggle('edited',row[k]!==original[index][k]);td.title=row[k]!==original[index][k]?translateText('Исправлено вручную'):'';td.style.background=row[k]?translateText(`var(--c-${k})`):'';renderRaw(raw,row);updateStats();};td.onblur=()=>renderTable();td.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();td.blur();}};tr.append(td);});const conf=create('td');conf.append(badge(row));tr.append(conf);$('tbody').append(tr);}$('page').textContent=translateText(`${list.length} записей · Страница ${page+1} из ${pages}`);$('prev').disabled=page===0;$('next').disabled=page>=pages-1;}
function renderDetail(target,index,editable){
  target.textContent='';
  if(index===undefined||!rows[index]){target.append(create('div',rows.length?translateText('Все выбранные адреса проверены.'):translateText('Сначала добавьте и обработайте адреса.'),'empty'));return;}
  const row=rows[index],grid=create('div',undefined,'detail'),left=create('div'),raw=create('div',undefined,'bigraw');
  renderRaw(raw,row);
  left.append(create('p',translateText(`Запись ${index+1} / ${rows.length}`),'eyebrow'),raw,badge(row));
  if(reviewed.has(index))left.append(create('p',translateText('✓ Проверено человеком'),'tag'));
  const checks=create('div',undefined,'record-checks');renderChecks(checks,row);left.append(checks);
  const fields=create('div',undefined,'fields');
  FIELDS.forEach(([key,label])=>{
    const box=create('div',undefined,'field');box.append(create('label',fieldLabel(row,key)));
    box.classList.toggle('edited',row[key]!==original[index][key]);
    const note=create('small',translateText('Не найдено в исходной строке'),'muted');
    const updateNote=()=>{note.hidden=!row[key]||ranges(row).some(range=>range[2]===key);};
    if(editable){
      const input=create('input');input.value=row[key]??'';input.setAttribute('aria-label',fieldLabel(row,key));input.dataset.field=key;
      input.oninput=()=>{row[key]=input.value.trim()||null;reviewed.delete(index);left.querySelector('.tag')?.remove();box.classList.toggle('edited',row[key]!==original[index][key]);box.title=row[key]!==original[index][key]?translateText('Исправлено вручную'):'';renderRaw(raw,row);updateNote();renderChecks(checks,row);updateStats();};
      input.onblur=()=>renderTable();box.append(input);
    }else box.append(create('div',row[key]??'—'));
    updateNote();box.append(note);fields.append(box);
  });grid.append(left,fields);target.append(grid);
}
function renderTokens(){tokenIndex=Math.max(0,Math.min(tokenIndex,rows.length-1));$('recordSelect').textContent='';for(let i=0;i<rows.length;i++){const option=create('option',translateText(`${i+1}. ${String(rows[i].raw_address??'').slice(0,80)}`));option.value=i;$('recordSelect').append(option);}$('recordSelect').value=tokenIndex;$('tokenPrev').disabled=!rows.length||tokenIndex===0;$('tokenNext').disabled=!rows.length||tokenIndex===rows.length-1;$('tokenUndo').disabled=!rows.length;renderDetail($('tokenDetail'),rows.length?tokenIndex:undefined,true);}
function queueItems(){return rows.map((r,i)=>i).filter(i=>($('queueAll').checked||needsReview(rows[i]))&&matchesQueueReason(rows[i])).sort((a,b)=>confidence(rows[a])-confidence(rows[b]));}
function renderQueue(){const items=queueItems(),pending=items.filter(i=>!reviewed.has(i));queueIndex=Math.max(0,Math.min(queueIndex,pending.length-1));const count=items.filter(i=>reviewed.has(i)).length;$('progressText').textContent=translateText(`Проверено ${count} из ${items.length}`);$('progress').max=items.length||1;$('progress').value=count;queueCurrentRow=pending[queueIndex]??null;renderDetail($('queueDetail'),queueCurrentRow??undefined,true);['confirm','fixConfirm','skip','queueBack'].forEach(id=>$(id).disabled=!pending.length);}
function confirm(){if(queueCurrentRow!==null&&rows[queueCurrentRow])reviewed.add(queueCurrentRow);refresh();}
function refresh(){updateStats();renderTable();if(activeTab==='tokens')renderTokens();if(activeTab==='queue')renderQueue();}
// API: raw_address и id передаются без очистки и нормализации.
function buildPayload(text){if(!text.trim())throw Error(translateText('Введите хотя бы один адрес'));if(/^[\s]*[\[{]/.test(text)){let data;try{data=JSON.parse(text);}catch{throw Error(translateText('Не удалось прочитать файл. Проверьте формат.'));}const list=Array.isArray(data)?data:(data.records||data.data||data.items||data.addresses||(Object.hasOwn(data,'raw_address')?[data]:null));if(!Array.isArray(list))throw Error(translateText('Не удалось прочитать файл. Проверьте формат.'));return list.map((item,i)=>{if(typeof item==='string')return {id:i+1,raw_address:item};if(!item||typeof item!=='object'||typeof item.raw_address!=='string')throw Error(translateText(`Запись ${i+1}: проверьте адрес.`));return {id:item.id,raw_address:item.raw_address};});}return text.split(/\r?\n/).filter(s=>s.trim()!=='').map((raw_address,i)=>({id:i+1,raw_address}));}
async function run(){let payload;try{payload=buildPayload($('input').value);if(!payload.length)throw Error(translateText('Список адресов пуст.'));}catch(e){status(e.message,true);return;}$('run').disabled=true;$('clear').disabled=true;$('run').classList.add('busy');$('parse').setAttribute('aria-busy','true');$('retry').hidden=true;const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),120000),start=performance.now();status(translateText(`Разбираем ${payload.length} адресов…${payload.length>1000?' Большой набор может занять больше времени.':''}`));try{const resp=await fetch('/parse/batch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:controller.signal});if(!resp.ok)throw Error(translateText('Сервис временно недоступен. Попробуйте позже.'));const data=await resp.json(),result=Array.isArray(data)?data:(data.results||data.records);if(!Array.isArray(result)||result.some(r=>!r||typeof r!=='object'||Array.isArray(r)))throw Error(translateText('Не удалось обработать адреса. Попробуйте ещё раз.'));rows=result;original=clone(rows);reviewed.clear();page=tokenIndex=queueIndex=0;refresh();status(translateText(`Готово: ${rows.length} адресов · ${((performance.now()-start)/1000).toFixed(2)} с · Нужна проверка: ${rows.filter(r=>confidence(r)<threshold).length}`));}catch(e){status(e.name==='AbortError'?translateText('Обработка заняла слишком много времени. Попробуйте меньший список.'):translateText('Сервис временно недоступен. Попробуйте позже.'),true);$('retry').hidden=false;}finally{clearTimeout(timeout);$('run').disabled=false;$('clear').disabled=false;$('run').classList.remove('busy');$('parse').removeAttribute('aria-busy');}}
async function readFile(file){if(!file)return;if(!/\.(txt|json)$/i.test(file.name)){status(translateText('Выберите файл .json или .txt'),true);return;}try{$('input').value=await file.text();status(translateText(`Загружен ${file.name}${file.size>5*1024*1024?' · Большой файл: обработка может занять время.':''}`));}catch{status(translateText('Не удалось прочитать файл.'),true);}}
function exportRows(){return rows.map((r,i)=>$('exportReviewed').checked?{...r,reviewed:reviewed.has(i)}:{...r});}
function download(name,mime,text){const url=URL.createObjectURL(new Blob([text],{type:mime})),a=create('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function csvText(data){const cols=[...new Set(data.flatMap(r=>Object.keys(r)))];const esc=v=>{const s=v==null?'':typeof v==='object'?JSON.stringify(v):String(v);return /[",;\r\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s;};return '\ufeff'+[cols.map(esc).join(','),...data.map(r=>cols.map(k=>esc(r[k])).join(','))].join('\r\n');}
$('run').onclick=$('retry').onclick=run;$('example').onclick=()=>{$('input').value=examples.join('\n');status(translateText('Примеры добавлены. Можно начать обработку.'));};$('clear').onclick=()=>{$('input').value='';rows=[];original=[];reviewed.clear();refresh();status(translateText('Очищено. Добавьте новые адреса.'));};$('file').onchange=e=>{readFile(e.target.files[0]);e.target.value='';};document.querySelector('label[for=file]').onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();$('file').click();}};$('drop').ondragover=e=>{e.preventDefault();$('drop').classList.add('over');};$('drop').ondragleave=()=>$('drop').classList.remove('over');$('drop').ondrop=e=>{e.preventDefault();$('drop').classList.remove('over');readFile(e.dataTransfer.files[0]);};
$('dlJson').onclick=()=>download('jana-address.json','application/json',JSON.stringify(exportRows(),null,2));$('dlCsv').onclick=()=>download('jana-address.csv','text/csv;charset=utf-8',csvText(exportRows()));$('copy').onclick=async()=>{try{await navigator.clipboard.writeText(JSON.stringify(exportRows(),null,2));status(translateText('Скопировано.'));}catch{status(translateText('Не удалось скопировать. Скачайте файл.'),true);}};
$('undo').onclick=()=>{rows=clone(original);reviewed.clear();refresh();};['search','sort','onlylow'].forEach(id=>$(id).addEventListener('input',()=>{page=0;renderTable();}));$('threshold').oninput=()=>{threshold=+$('threshold').value;save('jana-threshold',threshold);queueIndex=0;refresh();};$('prev').onclick=()=>{page--;renderTable();};$('next').onclick=()=>{page++;renderTable();};$('tokenPrev').onclick=()=>{tokenIndex--;renderTokens();};$('tokenNext').onclick=()=>{tokenIndex++;renderTokens();};$('recordSelect').onchange=()=>{tokenIndex=+$('recordSelect').value;renderTokens();};$('queueAll').onchange=()=>{queueIndex=0;renderQueue();};$('confirm').onclick=$('fixConfirm').onclick=confirm;$('fixConfirm').title=translateText('Измените поля и подтвердите');$('skip').onclick=()=>{const length=queueItems().filter(i=>!reviewed.has(i)).length;queueIndex=(queueIndex+1)%Math.max(1,length);renderQueue();};$('queueBack').onclick=()=>{queueIndex=Math.max(0,queueIndex-1);renderQueue();};document.addEventListener('keydown',e=>{if(activeTab!=='queue'||e.target.closest('input,textarea,select,button,[contenteditable]'))return;if(['Enter','ArrowRight','ArrowLeft'].includes(e.key)){e.preventDefault();if(e.key==='Enter')confirm();else $(e.key==='ArrowRight'?'skip':'queueBack').click();}});
renderLegends();refresh();
