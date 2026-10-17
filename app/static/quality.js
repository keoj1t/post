// Проверки помогают оператору, но не подменяют исходные поля.
function fieldLabel(row,key){
  if(key==='city'&&row.review?.locality_kind==='village')return translateText('Населённый пункт');
  if(key==='street_name'&&row.street_type==='квартал')return translateText('Квартал');
  if(key==='street_name'&&row.street_type==='микрорайон')return translateText('Микрорайон');
  return translateText(FIELDS.find(([name])=>name===key)?.[1]||key);
}
function reviewIssues(row){
  const current=(row.review?.issues||[]).filter(issue=>Object.entries(issue.observed||{}).every(([key,value])=>(row[key]??null)===(value??null)));
  const seen=new Set(current.map(issue=>issue.code));
  const local=(code,field,ru,kk,hintRu,hintKk)=>{if(!seen.has(code))current.push({code,field,severity:'warning',message:{ru,kk},suggestion:{ru:hintRu,kk:hintKk},candidates:[]});};
  if(!row.house)local('missing_house','house','Не найден номер дома.','Үй нөмірі табылмады.','Укажите номер дома по исходной строке.','Үй нөмірін бастапқы жол бойынша енгізіңіз.');
  if(!row.street_name&&!row.living_area)local('missing_street','street_name','Не найдена улица или жилмассив.','Көше не тұрғын алап табылмады.','Уточните название улицы или жилмассива.','Көше не тұрғын алап атауын нақтылаңыз.');
  if(!row.city)local('missing_city','city','Не найден город.','Қала табылмады.','Уточните город: это поможет проверить район и область.','Қаланы нақтылаңыз: бұл аудан мен облысты тексеруге көмектеседі.');
  if(row.postal_code&&!/^(?:[0-9]{6}|[a-z][0-9]{2}[a-z][0-9][a-z][0-9])$/i.test(row.postal_code))local('invalid_postal','postal_code','Необычный формат почтового индекса.','Пошта индексінің пішімі ерекше.','Проверьте индекс; не дополняйте его случайными цифрами.','Индексті тексеріңіз; кездейсоқ сан қоспаңыз.');
  if(confidence(row)<threshold&&!current.some(issue=>issue.severity==='warning'))local('low_confidence',null,'Уверенность ниже выбранного порога.','Сенімділік таңдалған шектен төмен.','Сверьте все поля и подтвердите результат вручную.','Барлық өрісті салыстырып, нәтижені қолмен растаңыз.');
  return current;
}
function recordChecks(row){return reviewIssues(row).filter(issue=>issue.severity==='warning').map(issue=>issue.message[language]||issue.message.ru);}
function needsReview(row){return confidence(row)<threshold||reviewIssues(row).some(issue=>issue.severity==='warning');}
function matchesQueueReason(row){
  const reason=$('queueReason')?.value||'all';
  return reason==='all'||reviewIssues(row).some(issue=>reason==='missing'?issue.code.startsWith('missing_'):reason==='geo'?issue.code.includes('geo')||issue.code.includes('city')||issue.code.includes('province'):reason==='postal'?issue.code.includes('postal'):issue.code.includes('conflict')||issue.code.includes('multiple')||issue.code.includes('overlap')||issue.code.includes('unassigned')||issue.code.includes('unbound'));
}
function renderChecks(target,row){
  target.textContent='';const issues=reviewIssues(row);target.hidden=!issues.length;
  if(!issues.length)return;
  target.append(create('strong',translateText('Почему нужна проверка')));
  const list=create('ul');
  for(const issue of issues){
    const item=create('li',undefined,issue.severity==='info'?'review-info':'review-warning');
    item.append(create('strong',issue.message[language]||issue.message.ru),create('p',issue.suggestion[language]||issue.suggestion.ru));
    if(issue.candidates?.length){const choices=create('div',undefined,'review-choices');for(const candidate of issue.candidates){const button=create('button',candidate.label);button.type='button';button.onclick=()=>{for(const [key,value] of Object.entries(candidate.changes||{}))if(FIELDS.some(([field])=>field===key))row[key]=value;const index=rows.indexOf(row);reviewed.delete(index);if(activeTab==='queue'){$('queueReason').value='all';queueIndex=Math.max(0,queueItems().filter(i=>!reviewed.has(i)).indexOf(index));}refresh();toast('Вариант применён. Проверьте и подтвердите.');};choices.append(button);}item.append(choices);}
    list.append(item);
  }
  target.append(list);
}
function updateValidationSummary(){
  const count=rows.filter(row=>recordChecks(row).length).length;
  $('validationSummary').hidden=!count;
  $('validationSummary').textContent=language==='kk'?`${count} мекенжайды тексеріңіз. Мәліметтер мен ескертулер мекенжай карточкасында көрсетілген.`:`Проверьте адреса: ${count}. Подсказки и замечания доступны в деталях каждого адреса.`;
}
const ERROR_CASES=JSON.parse($('errors-data').textContent);
function renderErrors(){
  const previous=$('errorCategory').value;
  $('errorCategory').textContent='';
  const all=create('option',translateText('Все категории'));all.value='';$('errorCategory').append(all);
  for(const key of new Set(ERROR_CASES.map(entry=>entry.category.ru))){const entry=ERROR_CASES.find(item=>item.category.ru===key),option=create('option',entry.category[language]);option.value=key;$('errorCategory').append(option);}
  $('errorCategory').value=previous;
  const category=$('errorCategory').value,query=$('errorSearch').value.toLocaleLowerCase();
  $('errorsBody').textContent='';
  for(const entry of ERROR_CASES){
    const text=[entry.example,entry.category[language],entry.before[language],entry.fix[language],...Object.values(entry.expected)].join(' ').toLocaleLowerCase();
    if((category&&category!==entry.category.ru)||(query&&!text.includes(query)))continue;
    const row=create('tr'),first=create('td');first.append(create('strong',entry.category[language]),create('p',entry.example));
    const result=create('td'),list=create('dl',undefined,'expected-fields');
    Object.entries(entry.expected).forEach(([key,value])=>{if(key==='confidence'){list.append(create('dt',translateText('Уверенность')),create('dd',`${Math.round(value*100)}%`));}else list.append(create('dt',fieldLabel(entry.expected,key)),create('dd',value??'—'));});
    result.append(create('span',translateText('Проверено тестом'),'badge good'),list);
    const action=create('td'),button=create('button',translateText('Проверить пример'));button.onclick=()=>{$('input').value=entry.example;tab('parse');run();};action.append(button);
    row.append(first,create('td',entry.before[language]),create('td',entry.fix[language]),result,action);$('errorsBody').append(row);
  }
  if(!$('errorsBody').children.length){const row=create('tr'),cell=create('td',translateText('Совпадений не найдено'),'empty');cell.colSpan=5;row.append(cell);$('errorsBody').append(row);}
}
$('errorSearch').oninput=$('errorCategory').onchange=renderErrors;
$('tokenDemo').onclick=async()=>{$('input').value='66квартал 12дом 69квартира';await run();if(rows.length)tab('tokens');};
$('tokenUndo').onclick=()=>{if(rows[tokenIndex])revert(tokenIndex);};
$('queueJson').onclick=()=>$('dlJson').click();$('queueCsv').onclick=()=>$('dlCsv').click();
$('queueReviewed').onchange=()=>{$('exportReviewed').checked=$('queueReviewed').checked;};
$('exportReviewed').onchange=()=>{$('queueReviewed').checked=$('exportReviewed').checked;};

$('queueReason').onchange=()=>{queueIndex=0;renderQueue();};
