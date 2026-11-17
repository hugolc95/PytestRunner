(() => {
  'use strict';
  const root=document.getElementById('pytest-tree-report-in');
  const data=JSON.parse(document.getElementById('report-data').textContent);
  const assets=JSON.parse(document.getElementById('report-icons').textContent);
  const nodes=data.nodes, rows=data.rows, readers=data.readers;
  for(const row of rows)for(const result of row.readers)result.yaml=data.configurations[result.configuration];
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const labels={passed:'Passed',failed:'Failed',error:'Error',skipped:'Skipped',notrun:'Not run',unknown:'Unknown',incomplete:'Incomplete'};
  const bad=s=>s==='failed'||s==='error';
  const iconStyle=document.createElement('style');
  iconStyle.textContent=Object.entries(assets).map(([name,url])=>`#pytest-tree-report-in .tr-icon-${name}{--tr-mask:url('${url}')}`).join('');
  root.append(iconStyle);
  const glyph=(name,extra='')=>`<span class="tr-glyph tr-icon-${assets[name]?name:'status-pending'} ${extra}" aria-hidden="true"></span>`;
  const verdict=(status,group=false)=>glyph((group?'group-':'status-')+(status==='unknown'?'pending':status));
  const facts=pairs=>`<dl class="tr-facts">${pairs.map(([label,value])=>`<dt>${esc(label)}</dt><dd>${esc(value)}</dd>`).join('')}</dl>`;
  const code=value=>`<pre class="tr-code">${esc(value)}</pre>`;
  const missing='Not recorded in this archive.';
  const descendants={};
  function fill(id){const n=nodes[id];return descendants[id]=n.kind==='test'?[n.index]:n.children.flatMap(fill);}
  fill('profile');
  const counts=list=>{const c={};for(const index of list)for(const result of rows[index].readers)c[result.status]=(c[result.status]||0)+1;return c;};
  const validTime=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0;
  const formatTime=value=>{
    if(!validTime(value))return '—';
    if(value===0)return '0.000s';
    if(value<1)return (value*1000).toFixed(value<.001?2:1).replace(/\.?0+$/,'')+' ms';
    if(value<60)return value.toFixed(3).replace(/\.?0+$/,'')+'s';
    const whole=Math.round(value*1000),hours=Math.floor(whole/3600000),minutes=Math.floor(whole%3600000/60000),seconds=(whole%60000/1000).toFixed(2).replace(/\.?0+$/,'');
    return (hours?hours+' h ':'')+minutes+' min '+seconds+'s';
  };
  const summaries={};
  for(const [id,list] of Object.entries(descendants)){
    summaries[id]={counts:counts(list),readers:readers.map((_,reader)=>{
      const results=list.map(i=>rows[i].readers[reader]);
      const values=results.map(result=>result.status);
      const measured=results.map(result=>result.attempts.at(-1)?.duration).filter(validTime);
      const status=['error','failed'].find(value=>values.includes(value))||(values.includes('unknown')?'unknown':values.every(value=>value==='notrun')?'notrun':values.includes('notrun')?'incomplete':values.includes('skipped')?'skipped':'passed');
      return {status,value:measured.reduce((sum,value)=>sum+value,0),known:measured.length,expected:results.filter(result=>result.status!=='notrun').length};
    })};
  }
  const aggregate=(id,reader)=>summaries[id].readers[reader].status;
  const searchable=rows.map(row=>[row.nodeid,row.name,...row.groups,...row.parents.map(id=>nodes[id].name+' '+(nodes[id].description||''))].join(' ').toLowerCase());
  const initial=rows.find(row=>row.readers.some(result=>bad(result.status)))||rows[0];
  const state={selected:initial?.id||'profile',reader:initial?Math.max(0,initial.readers.findIndex(result=>bad(result.status))):0,tab:'trace',attempt:-1,query:'',filter:'all',readerFilter:'all',expanded:new Set(['profile']),filtered:null};
  if(initial)for(const id of initial.parents)state.expanded.add(id);
  for(const id of nodes.profile.children)if(nodes[id].kind==='group')state.expanded.add(id);
  const ui=root.querySelector('.tr-ui');ui.hidden=false;root.classList.add('report-interactive');
  const search=root.querySelector('.tr-search'),statusFilter=root.querySelector('.tr-status-filter'),readerFilter=root.querySelector('.tr-reader-filter');
  readerFilter.innerHTML='<option value="all">All readers</option>'+readers.map((name,i)=>`<option value="${i}">${esc(name)}</option>`).join('');
  const cols=()=>state.readerFilter==='all'?readers.map((_,i)=>i):[Number(state.readerFilter)];
  const expansion=()=>state.filtered||state.expanded;
  const treeRoot=root.querySelector('.tr-tree'),inspector=root.querySelector('.tr-inspector');
  let allowed=new Set(),paneCache=new Map(),searchTimer=0;
  const bodyPanel=()=>inspector.querySelector('#tr-detail-panel');
  function matches(){const query=state.query.toLowerCase(),columns=cols();return rows.filter((row,index)=>searchable[index].includes(query)&&(state.filter==='all'||columns.some(i=>state.filter==='issues'?bad(row.readers[i].status):row.readers[i].status===state.filter)));}
  function filterChanged(){state.filtered=state.query||state.filter!=='all'?new Set(Object.keys(nodes)):null;renderTree();}
  function paintSelection(id,selected){
    const line=document.getElementById('tr-line-'+id);if(!line)return;
    line.classList.toggle('tr-selected',selected);
    line.querySelector('.tr-label')?.setAttribute('aria-pressed',String(selected));
    for(const button of line.querySelectorAll('.tr-verdict'))button.setAttribute('aria-pressed',String(selected&&Number(button.dataset.reader)===state.reader));
  }
  function select(id,reader){
    const previous=state.selected;
    state.selected=id;state.attempt=-1;
    if(reader!==undefined)state.reader=reader;
    else if(nodes[id].kind==='test')state.reader=state.readerFilter==='all'?Math.max(0,rows[nodes[id].index].readers.findIndex(result=>bad(result.status))):Number(state.readerFilter);
    let reveal=false;
    for(const parent of nodes[id].parents||[])if(!expansion().has(parent)){expansion().add(parent);reveal=true;}
    if(reveal)renderTree();else{paintSelection(previous,false);paintSelection(id,true);}
    renderInspector();
  }
  function timing(id){
    const t=cols().reduce((value,reader)=>{const r=summaries[id].readers[reader];value.value+=r.value;value.known+=r.known;value.expected+=r.expected;return value;},{value:0,known:0,expected:0});
    const partial=t.known>0&&t.known<t.expected;
    return {text:t.known?formatTime(t.value)+(partial?'*':''):'—',title:t.known?`${t.known} / ${t.expected} recorded durations${partial?' · Partial sum; missing durations are not zero':''}`:'No duration was recorded'};
  }
  function tree(id,depth,allowed){
    if(!allowed.has(id))return '';
    const n=nodes[id],branch=n.kind!=='test',open=expansion().has(id),isTest=n.kind==='test',row=isTest?rows[n.index]:null;
    const icon=({profile:'layers',group:'folder',folder:'folder-outline',module:'file-code',class:'kind-class',function:'braces',test:'flask-conical',case:'case'})[n.kind]||'folder-outline';
    const time=timing(id);
    return `<li class="tr-tree-item ${n.kind==='group'?'tr-group':''}" data-node="${id}" style="--depth:${depth};${n.color?'--group-color:'+n.color:''}"><div id="tr-line-${id}" class="tr-line ${state.selected===id?'tr-selected':''}"><div class="tr-name-cell">${branch?`<button type="button" class="tr-expand" data-toggle="${id}" aria-label="${open?'Collapse':'Expand'} ${esc(n.name)}" aria-expanded="${open}">${glyph(open?'chevron-down':'chevron-right')}</button>`:'<span class="tr-expand-spacer"></span>'}<button type="button" class="tr-label" data-select="${id}" aria-pressed="${state.selected===id}">${glyph(icon,'tr-node-icon')}<span class="tr-label-text">${esc(n.name)}${branch&&['profile','group'].includes(n.kind)?` <span class="tr-note">· ${descendants[id].length}</span><span class="tr-description">${esc(n.description||'')}</span>`:''}${row&&row.readers.some(result=>result.attempts.length>1)?glyph('retry','tr-retry-icon'):''}</span>${row?.custom?'<span class="tr-yaml-dot" aria-label="Custom YAML"></span>':''}</button></div>${cols().map(reader=>{const status=row?row.readers[reader].status:aggregate(id,reader);return `<button type="button" class="tr-verdict tr-${status}" data-select="${id}" data-reader="${reader}" aria-label="${esc(n.name)}, ${esc(readers[reader])}, ${labels[status]}" title="${esc(readers[reader])}: ${labels[status]}" aria-pressed="${state.selected===id&&state.reader===reader}">${verdict(status,branch)}</button>`;}).join('')}<span class="tr-duration" title="${esc(time.title)}">${esc(time.text)}</span></div>${branch&&open?`<ul class="tr-children">${n.children.map(child=>tree(child,depth+1,allowed)).join('')}</ul>`:''}</li>`;
  }
  function breadcrumb(n){return (n.parents||parents(n)).map(id=>nodes[id].name).join(' / ');}
  function parents(n){const ids=[];while(n.parent){ids.unshift(n.parent);n=nodes[n.parent];}return ids;}
  function groupDetail(n){
    const members=descendants[n.id],c=summaries[n.id].counts;
    return `<div class="tr-breadcrumb">${esc(breadcrumb(n))}</div><h3 class="tr-heading">${esc(n.name)}</h3><p class="tr-meta">${esc(n.description||'Execution hierarchy')}</p><div class="tr-selection-meta">${Object.entries(c).map(([status,value])=>`<span class="tr-${status}">${verdict(status)} ${value} ${labels[status]}</span>`).join('')}</div>${facts([['Occurrences',members.length],['Readers',readers.length],['Scope','All descendants, including collapsed and filtered rows.']])}<table class="tr-table"><thead><tr><th>Reader</th><th>Duration</th><th>Measured</th></tr></thead><tbody>${summaries[n.id].readers.map((r,i)=>`<tr><td>${esc(readers[i])}</td><td>${r.known?esc(formatTime(r.value)):'—'}</td><td>${r.known} / ${r.expected}</td></tr>`).join('')}</tbody></table><p class="tr-caption">Durations are sums of the latest recorded attempts, not elapsed run time. An asterisk marks a partial sum.</p><details class="tr-members" data-members="${n.id}"><summary>Occurrences in profile order (${members.length})</summary><div class="tr-member-list"></div></details>`;
  }
  function showMembers(details,page=0){
    const list=descendants[details.dataset.members],start=page*100;
    details.querySelector('.tr-member-list').innerHTML=`<ol class="tr-group-members" start="${start+1}">${list.slice(start,start+100).map(index=>`<li><button type="button" data-select="${rows[index].id}">${esc(rows[index].nodeid)} · #${index+1}</button></li>`).join('')}</ol>${list.length>100?`<div class="tr-tools"><span class="tr-note">${start+1}–${Math.min(start+100,list.length)} / ${list.length}</span><button type="button" class="tr-button" data-members-page="${page-1}" ${page===0?'disabled':''}>Previous</button><button type="button" class="tr-button" data-members-page="${page+1}" ${start+100>=list.length?'disabled':''}>Next</button></div>`:''}`;
    details.dataset.loaded='true';
  }
  const displayValue=value=>typeof value==='string'?(value===''?'""':value):JSON.stringify(value);
  function body(row,result,attempt){
    if(state.tab==='yaml'){
      const y=result.yaml;
      return `${y.notice?`<p class="tr-meta">${esc(y.notice)}</p>`:''}<div class="tr-meta">Effective parameter values at launch</div><table class="tr-table tr-parameters"><thead><tr><th scope="col">Parameter</th><th scope="col">Value</th></tr></thead><tbody>${(y.parameters||[]).map(parameter=>`<tr><td>${esc(parameter.parameter)}</td><td><code class="tr-value">${esc(displayValue(parameter.value))}</code></td></tr>`).join('')}</tbody></table><details><summary>Parameter origins</summary><table class="tr-table"><thead><tr><th>Parameter</th><th>Origin</th></tr></thead><tbody>${y.origins.map(origin=>`<tr><td>${esc(origin.parameter)}</td><td>${esc(origin.source)}</td></tr>`).join('')}</tbody></table></details><details><summary>Effective YAML</summary>${code(y.effective||missing)}</details><details><summary>Base YAML captured at launch</summary>${code(y.base||missing)}</details>`;
    }
    if(state.tab==='logs')return attempt?.log?`${attempt.log_shared?'<p class="tr-meta">This file was shared by multiple occurrences.</p>':''}<div class="tr-meta">${esc(attempt.log_path||'Archived test log')}</div>${code(attempt.log)}`:`<p class="tr-meta">${esc(result.status==='notrun'?result.notice||'Not executed: no log was produced.':attempt?.log_notice||'No individual log was archived. Full recorded output is available in Console output below.')}</p>`;
    if(state.tab==='trace')return attempt?.trace?`${attempt.message?`<div class="tr-issue tr-${attempt.status}">${esc(attempt.message)}</div>`:''}${code(attempt.trace)}`:`<p class="tr-meta">${esc(result.status==='notrun'?result.notice||'Not executed: no traceback.':result.status==='unknown'?missing:attempt?.status==='passed'?'No error in this recorded attempt.':'No traceback was archived. Check the recorded console output.')}</p>`;
    return facts([['Node ID',row.nodeid],['Group path',row.groups.join(' → ')||'No named group'],['Occurrence',`${row.index+1} / ${rows.length} · Repetition ${row.repetition} · Step ${row.step}`],['Source path',row.file],['Reader',readers[state.reader]],['Final result',labels[result.status]],['Phase',attempt?.phase||missing],['Duration',attempt?.duration===undefined||attempt.duration===null?missing:formatTime(attempt.duration)],['Duration source',validTime(attempt?.duration)?attempt.duration_source||'Recorded for this attempt':missing],['Recorded attempts',result.attempts.length],['Archive note',result.notice||'Occurrence recorded independently.']]);
  }
  function detail(n){
    if(n.kind!=='test')return groupDetail(n);
    const row=rows[n.index],result=row.readers[state.reader],index=state.attempt<0?result.attempts.length-1:state.attempt,attempt=result.attempts[index];
    return `<div class="tr-breadcrumb">${esc(breadcrumb(n))}</div><h3 class="tr-heading">${esc(row.name)}</h3><div class="tr-meta">Occurrence ${row.index+1} / ${rows.length} · Repetition ${row.repetition} · Step ${row.step}</div><select class="tr-reader-choice" aria-label="Reader for selected test">${readers.map((reader,i)=>`<option value="${i}" ${i===state.reader?'selected':''}>${esc(reader)}</option>`).join('')}</select><div class="tr-selection-meta"><span class="tr-${attempt?.status||result.status}">${verdict(attempt?.status||result.status)} ${labels[attempt?.status||result.status]}</span><span>${esc(attempt?.phase||'')}</span><span>${validTime(attempt?.duration)?formatTime(attempt.duration):'Duration not recorded'}</span></div>${result.attempts.length>1?`<select class="tr-attempt" aria-label="Recorded attempt">${result.attempts.map((a,i)=>`<option value="${i}" ${i===index?'selected':''}>Attempt ${i+1} — ${labels[a.status]}${i===result.attempts.length-1?' · Latest':''}</option>`).join('')}</select>`:''}<div class="tr-tabs" role="tablist" aria-label="Result details">${[['summary','Details'],['trace','Traceback'],['logs','Logs'],['yaml','YAML']].map(([id,label])=>`<button type="button" class="tr-tab" id="tr-tab-${id}" role="tab" aria-controls="tr-detail-panel" aria-selected="${state.tab===id}" data-tab="${id}">${label}</button>`).join('')}</div><div id="tr-detail-panel" role="tabpanel" aria-labelledby="tr-tab-${state.tab}">${body(row,result,attempt)}</div>`;
  }
  function renderInspector(){
    paneCache=new Map();
    inspector.innerHTML='<p class="tr-caption tr-selection-filter-note" hidden></p>'+detail(nodes[state.selected]);
    updateSelectionNotice();
  }
  function updateSelectionNotice(){
    const note=inspector.querySelector('.tr-selection-filter-note');if(!note)return;
    note.hidden=allowed.has(state.selected);note.textContent='Selected item is outside the current filters.';
  }
  function changeTab(tab){
    if(state.tab===tab)return;
    const panel=bodyPanel();if(!panel)return;
    const fragment=document.createDocumentFragment();
    while(panel.firstChild)fragment.append(panel.firstChild);
    paneCache.set(state.tab,fragment);state.tab=tab;
    if(paneCache.has(tab)){panel.append(paneCache.get(tab));paneCache.delete(tab);}
    else{const row=rows[nodes[state.selected].index],result=row.readers[state.reader];panel.innerHTML=body(row,result,result.attempts[state.attempt<0?result.attempts.length-1:state.attempt]);}
    for(const button of inspector.querySelectorAll('[data-tab]'))button.setAttribute('aria-selected',String(button.dataset.tab===tab));
    panel.setAttribute('aria-labelledby','tr-tab-'+tab);
  }
  function renderTree(){
    const list=matches();allowed=new Set(list.flatMap(row=>[row.id,...row.parents]));
    root.style.setProperty('--tr-readers',String(cols().length));
    root.querySelector('.tr-tree-head').innerHTML='<span>Profile / groups / tests</span>'+cols().map(i=>`<span class="tr-reader-heading" title="${esc(readers[i])}">${esc(data.badges[i])}</span>`).join('')+'<span class="tr-duration" title="Sum of latest recorded attempt durations">Duration</span>';
    root.querySelector('.tr-filter-count').textContent=`${list.length} / ${rows.length} occurrences shown · Run totals remain unchanged`;
    treeRoot.innerHTML=list.length?tree('profile',0,allowed):'<li class="tr-caption">No matching test.</li>';
    updateSelectionNotice();
  }
  function toggleBranch(button){
    const id=button.dataset.toggle,li=button.closest('li'),open=!expansion().has(id);
    if(open){expansion().add(id);li.insertAdjacentHTML('beforeend',`<ul class="tr-children">${nodes[id].children.map(child=>tree(child,parents(nodes[id]).length+1,allowed)).join('')}</ul>`);}
    else{expansion().delete(id);li.querySelector(':scope > .tr-children')?.remove();}
    button.setAttribute('aria-expanded',String(open));button.setAttribute('aria-label',(open?'Collapse ':'Expand ')+nodes[id].name);button.innerHTML=glyph(open?'chevron-down':'chevron-right');
  }
  const context=root.querySelector('.tr-context-body');
  context.innerHTML=facts([['Run ID',data.id],['Workspace',data.workspace],['Origin',data.run_kind],['Profile structure',data.profile_recorded?'Captured at launch':'Not recorded in this older archive'],['Configuration',data.configuration_name||missing]])+data.contexts.map(c=>`<details><summary>${esc(c.reader)} · Exit code ${c.exit_code}</summary>${facts([['Interpreter',c.interpreter],['Python / pytest',c.session],['ATR at launch',c.atr],['Runner at launch',c.app_version]])}${c.issues.length?code(c.issues.join('\n\n')):''}${c.commands.length?c.commands.map(command=>code(command.map(arg=>/\s/.test(arg)?JSON.stringify(arg):arg).join(' '))).join(''):code('Command: '+missing)}</details>`).join('');
  root.querySelector('.tr-console').innerHTML=data.console.map((_,i)=>`<details data-console="${i}"><summary>${esc(readers[i])}</summary></details>`).join('');
  root.addEventListener('toggle',event=>{
    const details=event.target;
    if(details.matches('[data-members]')&&details.open&&!details.dataset.loaded)showMembers(details);
    if(details.matches('[data-console]')&&details.open&&!details.dataset.loaded){
      const pre=document.createElement('pre');pre.className='tr-code';pre.textContent=data.console[Number(details.dataset.console)]||missing;details.append(pre);details.dataset.loaded='true';
    }
  },true);
  root.querySelector('.tr-legend').innerHTML=Object.entries(labels).map(([status,label])=>`<span class="tr-${status}">${verdict(status)} ${label}</span>`).join('');
  for(const item of root.querySelectorAll('.tr-summary > span')){const status=item.dataset.status;if(status)item.insertAdjacentHTML('afterbegin',verdict(status));}
  root.addEventListener('click',event=>{
    const toggle=event.target.closest('[data-toggle]');if(toggle){toggleBranch(toggle);return;}
    const selected=event.target.closest('[data-select]');if(selected){select(selected.dataset.select,selected.dataset.reader===undefined?undefined:Number(selected.dataset.reader));return;}
    const tab=event.target.closest('[data-tab]');if(tab){changeTab(tab.dataset.tab);return;}
    const memberPage=event.target.closest('[data-members-page]');if(memberPage){showMembers(memberPage.closest('[data-members]'),Number(memberPage.dataset.membersPage));return;}
    const action=event.target.closest('[data-action]');if(action){const expanded=action.dataset.action==='expand'?new Set(Object.keys(nodes)):new Set(['profile']);if(state.filtered)state.filtered=expanded;else state.expanded=expanded;renderTree();}
  });
  inspector.addEventListener('change',event=>{
    if(event.target.matches('.tr-reader-choice')){state.reader=Number(event.target.value);state.attempt=-1;paintSelection(state.selected,true);renderInspector();}
    else if(event.target.matches('.tr-attempt')){state.attempt=Number(event.target.value);renderInspector();}
  });
  search.addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{state.query=search.value;filterChanged();},100);});
  search.addEventListener('keydown',event=>{if(event.key==='Enter'){clearTimeout(searchTimer);state.query=search.value;filterChanged();}});
  statusFilter.addEventListener('change',()=>{clearTimeout(searchTimer);state.query=search.value;state.filter=statusFilter.value;filterChanged();});
  readerFilter.addEventListener('change',()=>{clearTimeout(searchTimer);state.query=search.value;state.readerFilter=readerFilter.value;if(state.readerFilter!=='all')state.reader=Number(state.readerFilter);filterChanged();renderInspector();});
  renderTree();renderInspector();
})();
