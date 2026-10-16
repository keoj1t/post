// Проверки помогают оператору, но не подменяют исходные поля.
function fieldLabel(row,key){
  if(key==='street_name'&&row.street_type==='квартал')return translateText('Квартал');
  if(key==='street_name'&&row.street_type==='микрорайон')return translateText('Микрорайон');
  return translateText(FIELDS.find(([name])=>name===key)?.[1]||key);
}
function recordChecks(row){
  const checks=[];
  if(!row.house)checks.push(translateText('Не указан дом.'));
  if(!row.street_name&&!row.living_area)checks.push(translateText('Не указана улица или жилмассив.'));
  if(!row.city)checks.push(translateText('Не указан город.'));
  const normalize=value=>String(value||'').toLocaleLowerCase().replace(/(?:^|\s)(?:город|область)(?=\s|$)/gu,'').replace(/(?:қаласы|облысы)/gu,'').trim();
  const city=String(row.city||'').toLocaleLowerCase().trim(),province=normalize(row.province);
  const independent={'астана':'астана','нур-султан':'астана','алматы':'алматы','шымкент':'шымкент'};
  if(independent[city]&&province&&province!==independent[city])checks.push(translateText('Город и область не согласованы. Проверьте географию.'));
  if(confidence(row)<threshold)checks.push(translateText('Низкая уверенность: проверьте поля перед подтверждением.'));
  return checks;
}
function renderChecks(target,row){
  target.textContent='';
  const checks=recordChecks(row);
  target.hidden=!checks.length;
  if(checks.length){target.append(create('strong',translateText('Обратите внимание')));const list=create('ul');checks.forEach(text=>list.append(create('li',text)));target.append(list);}
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
