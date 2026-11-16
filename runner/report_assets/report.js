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
  const glyph=(name,extra='')=>`<span class="tr-glyph ${extra}" aria-hidden="true" style="--tr-mask:url('${assets[name]||assets['status-pending']}')"></span>`;
  const verdict=(status,group=false)=>glyph((group?'group-':'status-')+(status==='unknown'?'pending':status));
  const facts=pairs=>`<dl class="tr-facts">${pairs.map(([label,value])=>`<dt>${esc(label)}</dt><dd>${esc(value)}</dd>`).join('')}</dl>`;
  const code=value=>`<pre class="tr-code">${esc(value)}</pre>`;
  const missing='Not recorded in this archive.';
  const descendants={};
  function fill(id){const n=nodes[id];return descendants[id]=n.kind==='test'?[n.index]:n.children.flatMap(fill);}
  fill('profile');
  const counts=list=>{const c={};for(const index of list)for(const result of rows[index].readers)c[result.status]=(c[result.status]||0)+1;return c;};
  const aggregate=(id,reader)=>{
    const values=descendants[id].map(i=>rows[i].readers[reader].status);
    return ['error','failed'].find(s=>values.includes(s))||(values.includes('unknown')?'unknown':values.every(s=>s==='notrun')?'notrun':values.includes('notrun')?'incomplete':values.includes('skipped')?'skipped':'passed');
  };
  const initial=rows.find(row=>row.readers.some(result=>bad(result.status)))||rows[0];
  const state={selected:initial?.id||'profile',reader:initial?Math.max(0,initial.readers.findIndex(result=>bad(result.status))):0,tab:'trace',attempt:-1,query:'',filter:'all',readerFilter:'all',expanded:new Set(['profile']),filtered:null};
  if(initial)for(const id of initial.parents)state.expanded.add(id);
  for(const id of nodes.profile.children)if(nodes[id].kind==='group')state.expanded.add(id);
  const ui=root.querySelector('.tr-ui');ui.hidden=false;root.classList.add('report-interactive');
  const search=root.querySelector('.tr-search'),statusFilter=root.querySelector('.tr-status-filter'),readerFilter=root.querySelector('.tr-reader-filter');
  readerFilter.innerHTML='<option value="all">All readers</option>'+readers.map((name,i)=>`<option value="${i}">${esc(name)}</option>`).join('');
  const cols=()=>state.readerFilter==='all'?readers.map((_,i)=>i):[Number(state.readerFilter)];
  const expansion=()=>state.filtered||state.expanded;
  function matches(){return rows.filter(row=>{
    const text=[row.nodeid,row.name,...row.groups,...row.parents.map(id=>nodes[id].name+' '+(nodes[id].description||''))].join(' ').toLowerCase();
    return text.includes(state.query.toLowerCase())&&(state.filter==='all'||cols().some(i=>state.filter==='issues'?bad(row.readers[i].status):row.readers[i].status===state.filter));
  });}
  function filterChanged(){state.filtered=state.query||state.filter!=='all'?new Set(Object.keys(nodes)):null;render();}
  function select(id,reader){state.selected=id;state.attempt=-1;if(reader!==undefined)state.reader=reader;else if(nodes[id].kind==='test')state.reader=state.readerFilter==='all'?Math.max(0,rows[nodes[id].index].readers.findIndex(r=>bad(r.status))):Number(state.readerFilter);for(const parent of nodes[id].parents||[])expansion().add(parent);render();}
  function tree(id,depth,allowed){
    if(!allowed.has(id))return '';
    const n=nodes[id],branch=n.children.length>0,open=expansion().has(id),isTest=n.kind==='test',row=isTest?rows[n.index]:null;
    const icon=({profile:'layers',group:'folder',folder:'folder-outline',module:'file-code',class:'kind-class',function:'braces',test:'flask-conical',case:'case'})[n.kind]||'folder-outline';
    const time=descendants[id].reduce((sum,index)=>sum+cols().reduce((subtotal,reader)=>subtotal+(rows[index].readers[reader].attempts.at(-1)?.duration||0),0),0);
    return `<li class="tr-tree-item ${n.kind==='group'?'tr-group':''}" data-node="${id}" style="--depth:${depth};${n.color?'--group-color:'+n.color:''}"><div class="tr-line ${state.selected===id?'tr-selected':''}"><div class="tr-name-cell">${branch?`<button type="button" class="tr-expand" data-toggle="${id}" aria-label="${open?'Collapse':'Expand'} ${esc(n.name)}" aria-expanded="${open}">${glyph(open?'chevron-down':'chevron-right')}</button>`:'<span class="tr-expand-spacer"></span>'}<button type="button" class="tr-label" data-select="${id}" aria-pressed="${state.selected===id}">${glyph(icon,'tr-node-icon')}<span class="tr-label-text">${esc(n.name)}${branch&&['profile','group'].includes(n.kind)?` <span class="tr-note">· ${descendants[id].length}</span><span class="tr-description">${esc(n.description||'')}</span>`:''}${row&&row.readers.some(result=>result.attempts.length>1)?glyph('retry','tr-retry-icon'):''}</span>${row?.custom?'<span class="tr-yaml-dot" aria-label="Custom YAML"></span>':''}</button></div>${cols().map(reader=>{const status=row?row.readers[reader].status:aggregate(id,reader);return `<button type="button" class="tr-verdict tr-${status}" data-select="${id}" data-reader="${reader}" aria-label="${esc(n.name)}, ${esc(readers[reader])}, ${labels[status]}" title="${esc(readers[reader])}: ${labels[status]}" aria-pressed="${state.selected===id&&state.reader===reader}">${verdict(status,branch)}</button>`;}).join('')}<span class="tr-duration">${time?time.toFixed(2)+'s':'—'}</span></div>${branch&&open?`<ul class="tr-children">${n.children.map(child=>tree(child,depth+1,allowed)).join('')}</ul>`:''}</li>`;
  }
  function breadcrumb(n){return (n.parents||parents(n)).map(id=>nodes[id].name).join(' / ');}
  function parents(n){const ids=[];while(n.parent){ids.unshift(n.parent);n=nodes[n.parent];}return ids;}
  function groupDetail(n){const members=descendants[n.id],c=counts(members);return `<div class="tr-breadcrumb">${esc(breadcrumb(n))}</div><h3 class="tr-heading">${esc(n.name)}</h3><p class="tr-meta">${esc(n.description||'Execution hierarchy')}</p><div class="tr-selection-meta">${Object.entries(c).map(([status,value])=>`<span class="tr-${status}">${verdict(status)} ${value} ${labels[status]}</span>`).join('')}</div>${facts([['Occurrences',members.length],['Readers',readers.length],['Scope','All descendants, including collapsed and filtered rows.'],['Duration','Σ time sums recorded latest-attempt durations; it is not run wall time.']])}<ol class="tr-group-members">${members.map(index=>`<li><button type="button" data-select="${rows[index].id}">${esc(rows[index].nodeid)} · #${index+1}</button></li>`).join('')}</ol>`;}
  function body(row,result,attempt){
    if(state.tab==='yaml'){const y=result.yaml;return `${y.notice?`<p class="tr-meta">${esc(y.notice)}</p>`:''}<div class="tr-meta">Effective YAML at launch</div>${code(y.effective||missing)}<table class="tr-table"><thead><tr><th>Parameter</th><th>Origin</th></tr></thead><tbody>${y.origins.map(origin=>`<tr><td>${esc(origin.parameter)}</td><td>${esc(origin.source)}</td></tr>`).join('')}</tbody></table><details><summary>Base YAML captured at launch</summary>${code(y.base||missing)}</details>`;}
    if(state.tab==='logs')return attempt?.log?`${attempt.log_shared?'<p class="tr-meta">This file was shared by multiple occurrences.</p>':''}<div class="tr-meta">${esc(attempt.log_path||'Archived test log')}</div>${code(attempt.log)}`:`<p class="tr-meta">${esc(result.status==='notrun'?'Not executed: no log was produced.':attempt?.log_notice||'No individual log was archived. Full recorded output is available in Console output below.')}</p>`;
    if(state.tab==='trace')return attempt?.trace?`${attempt.message?`<div class="tr-issue tr-${attempt.status}">${esc(attempt.message)}</div>`:''}${code(attempt.trace)}`:`<p class="tr-meta">${esc(result.status==='notrun'?'Not executed: no traceback.':result.status==='unknown'?missing:attempt?.status==='passed'?'No error in this recorded attempt.':'No traceback was archived. Check the recorded console output.')}</p>`;
    return facts([['Node ID',row.nodeid],['Group path',row.groups.join(' → ')||'No named group'],['Occurrence',`${row.index+1} / ${rows.length} · Repetition ${row.repetition} · Step ${row.step}`],['Source path',row.file],['Reader',readers[state.reader]],['Final result',labels[result.status]],['Phase',attempt?.phase||missing],['Duration',attempt?.duration===undefined||attempt.duration===null?missing:attempt.duration.toFixed(3)+'s'],['Recorded attempts',result.attempts.length],['Archive note',result.notice||'Occurrence recorded independently.']]);
  }
  function detail(n){
    if(n.kind!=='test')return groupDetail(n);
    const row=rows[n.index],result=row.readers[state.reader],index=state.attempt<0?result.attempts.length-1:state.attempt,attempt=result.attempts[index];
    return `<div class="tr-breadcrumb">${esc(breadcrumb(n))}</div><h3 class="tr-heading">${esc(row.name)}</h3><div class="tr-meta">Occurrence ${row.index+1} / ${rows.length} · Repetition ${row.repetition} · Step ${row.step}</div><select class="tr-reader-choice" aria-label="Reader for selected test">${readers.map((reader,i)=>`<option value="${i}" ${i===state.reader?'selected':''}>${esc(reader)}</option>`).join('')}</select><div class="tr-selection-meta"><span class="tr-${attempt?.status||result.status}">${verdict(attempt?.status||result.status)} ${labels[attempt?.status||result.status]}</span><span>${esc(attempt?.phase||'')}</span><span>${attempt?.duration===undefined||attempt.duration===null?'':attempt.duration.toFixed(3)+'s'}</span></div>${result.attempts.length>1?`<select class="tr-attempt" aria-label="Recorded attempt">${result.attempts.map((a,i)=>`<option value="${i}" ${i===index?'selected':''}>Attempt ${i+1} — ${labels[a.status]}${i===result.attempts.length-1?' · Latest':''}</option>`).join('')}</select>`:''}<div class="tr-tabs" role="tablist" aria-label="Result details">${[['summary','Details'],['trace','Traceback'],['logs','Logs'],['yaml','YAML']].map(([id,label])=>`<button type="button" class="tr-tab" id="tr-tab-${id}" role="tab" aria-controls="tr-detail-panel" aria-selected="${state.tab===id}" data-tab="${id}">${label}</button>`).join('')}</div><div id="tr-detail-panel" role="tabpanel" aria-labelledby="tr-tab-${state.tab}">${body(row,result,attempt)}</div>`;
  }
  function render(){const list=matches(),allowed=new Set(list.flatMap(row=>[row.id,...row.parents]));root.style.setProperty('--tr-readers',String(cols().length));root.querySelector('.tr-tree-head').innerHTML='<span>Profile / groups / tests</span>'+cols().map(i=>`<span title="${esc(readers[i])}">${esc(data.badges[i])}</span>`).join('')+'<span class="tr-duration">Σ time</span>';root.querySelector('.tr-filter-count').textContent=`${list.length} / ${rows.length} occurrences shown · Run totals remain unchanged`;root.querySelector('.tr-tree').innerHTML=list.length?tree('profile',0,allowed):'<li class="tr-caption">No matching test.</li>';root.querySelector('.tr-inspector').innerHTML=detail(nodes[state.selected]);const choice=root.querySelector('.tr-reader-choice');if(choice)choice.addEventListener('change',()=>{state.reader=Number(choice.value);state.attempt=-1;render();});const attempt=root.querySelector('.tr-attempt');if(attempt)attempt.addEventListener('change',()=>{state.attempt=Number(attempt.value);render();});}
  const context=root.querySelector('.tr-context-body');
  context.innerHTML=facts([['Run ID',data.id],['Workspace',data.workspace],['Origin',data.run_kind],['Profile structure',data.profile_recorded?'Captured at launch':'Not recorded in this older archive'],['Configuration',data.configuration_name||missing]])+data.contexts.map(c=>`<details><summary>${esc(c.reader)} · Exit code ${c.exit_code}</summary>${facts([['Interpreter',c.interpreter],['Python / pytest',c.session],['ATR at launch',c.atr],['Runner at launch',c.app_version]])}${c.issues.length?code(c.issues.join('\n\n')):''}${c.commands.length?c.commands.map(command=>code(command.map(arg=>/\s/.test(arg)?JSON.stringify(arg):arg).join(' '))).join(''):code('Command: '+missing)}</details>`).join('');
  root.querySelector('.tr-console').innerHTML=data.console.map((output,i)=>`<details><summary>${esc(readers[i])}</summary>${code(output||missing)}</details>`).join('');
  root.querySelector('.tr-legend').innerHTML=Object.entries(labels).map(([status,label])=>`<span class="tr-${status}">${verdict(status)} ${label}</span>`).join('');
  for(const item of root.querySelectorAll('.tr-summary > span')){const status=item.dataset.status;if(status)item.insertAdjacentHTML('afterbegin',verdict(status));}
  root.addEventListener('click',event=>{const t=event.target.closest('[data-toggle]');if(t){const id=t.dataset.toggle;expansion().has(id)?expansion().delete(id):expansion().add(id);render();return;}const selected=event.target.closest('[data-select]');if(selected){select(selected.dataset.select,selected.dataset.reader===undefined?undefined:Number(selected.dataset.reader));return;}const tab=event.target.closest('[data-tab]');if(tab){state.tab=tab.dataset.tab;render();root.querySelector('#tr-tab-'+state.tab)?.focus();return;}const action=event.target.closest('[data-action]');if(action){const expanded=action.dataset.action==='expand'?new Set(Object.keys(nodes)):new Set(['profile']);if(state.filtered)state.filtered=expanded;else state.expanded=expanded;render();}});
  search.addEventListener('input',()=>{state.query=search.value;filterChanged();});
  statusFilter.addEventListener('change',()=>{state.filter=statusFilter.value;filterChanged();});
  readerFilter.addEventListener('change',()=>{state.readerFilter=readerFilter.value;if(state.readerFilter!=='all')state.reader=Number(state.readerFilter);filterChanged();});
  render();
})();
