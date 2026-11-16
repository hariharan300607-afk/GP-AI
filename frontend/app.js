const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const money = n => new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',minimumFractionDigits:0,maximumFractionDigits:2}).format(Number(n)||0);
const now = new Date();
const today = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
const API = '/api';
let transactions = [];
let dashboard = null;
let budgets = [];
let cashflowChart = null;
let categoryChart = null;

async function api(path, options={}) {
 const response = await fetch(`${API}${path}`, {headers:{'Content-Type':'application/json',...(options.headers||{})},...options});
 if(!response.ok){
  let message=`Request failed (${response.status})`;
  try{
   const data=await response.json(),detail=data.detail;
   message=Array.isArray(detail)?detail.map(item=>item.msg).join(' '):(detail||message);
  }catch{}
  throw new Error(message);
 }
 return response.json();
}
function toast(message, isError=false){
 const node=$('#toast'); if(!node)return;
 node.textContent=message; node.style.background=isError?'#512b2b':'#17251c';node.classList.add('show');
 clearTimeout(toast.timer);toast.timer=setTimeout(()=>node.classList.remove('show'),3200);
}
function iconFor(cat){return ({'Food & Dining':'utensils','Shopping':'shopping-bag','Transport':'car','Income':'wallet','Entertainment':'clapperboard','Groceries':'shopping-basket','Bills & Utilities':'receipt','Healthcare':'heart-pulse','Education':'book-open','Housing':'house','Fitness':'dumbbell'})[cat]||'circle-dollar-sign'}
function setupShell(){
 const page=document.body.dataset.page;
 $$('.nav a').forEach(a=>{if(a.dataset.page===page)a.classList.add('active')});
 const side=$('.sidebar'),toggle=$('.mobile-menu');
 if(toggle&&side)toggle.addEventListener('click',()=>side.classList.toggle('open'));
 $$('.add-transaction').forEach(b=>b.addEventListener('click',openModal));
 const close=$('.close-modal');if(close)close.addEventListener('click',closeModal);
 const backdrop=$('#transaction-modal');if(backdrop)backdrop.addEventListener('click',e=>{if(e.target===backdrop)closeModal()});
 const dateInput=$('#tx-date');if(dateInput&&!dateInput.value)dateInput.value=today;
 setupBudgetEditor();
 const form=$('#transaction-form');
 if(form)form.addEventListener('submit',async e=>{
  e.preventDefault();
  const merchant=$('#tx-description').value.trim(),amount=Number($('#tx-amount').value),type=$('#tx-type').value,date=$('#tx-date').value;
  if(!merchant||!amount||amount<=0)return;
  const category=$('#tx-category').value;
  const submit=form.querySelector('button[type="submit"]');
  if(submit){submit.disabled=true;submit.textContent='Saving transaction…'}
  try{
   const saved=await api('/transactions',{method:'POST',body:JSON.stringify({date,merchant,amount,type,category,method:$('#tx-method').value})});
   form.reset();$('#tx-date').value=today;closeModal();await refreshData();renderAll();
   const confidence=saved.category_confidence==null?'manual category':`${Math.round(saved.category_confidence*100)}% rule confidence`;
   toast(`Saved · ${saved.category} · ${confidence}`);
  }catch(err){toast(err.message,true)}
  finally{if(submit){submit.disabled=false;submit.innerHTML='Save transaction <i data-lucide="arrow-up-right"></i>';if(window.lucide)lucide.createIcons()}}
 });
 const search=$('#global-search');if(search)search.addEventListener('input',()=>{$$('tbody tr').forEach(r=>r.style.display=r.innerText.toLowerCase().includes(search.value.toLowerCase())?'':'none')});
}
function openModal(){const m=$('#transaction-modal');if(m)m.classList.add('open')}
function closeModal(){const m=$('#transaction-modal');if(m)m.classList.remove('open')}
async function refreshData(){
 [transactions,dashboard,budgets]=await Promise.all([api('/transactions'),api('/dashboard'),api('/budgets')]);
}
function renderTable(target,rows,limit=99){
 if(!target)return;
 const showActions=target.id==='all-rows';
 target.innerHTML=rows.slice().sort((a,b)=>b.id-a.id).slice(0,limit).map(t=>`<tr><td><div class="merchant"><span class="merchant-icon"><i data-lucide="${iconFor(t.category)}"></i></span>${escapeHtml(t.merchant)}</div></td><td><span class="category">${escapeHtml(t.category)}</span></td><td>${new Date(t.date+'T00:00:00').toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'})}</td><td>${escapeHtml(t.method||'UPI')}</td><td class="amount ${t.type==='Income'?'positive':'negative'}">${t.type==='Income'?'+':'−'}${money(t.amount)}</td>${showActions?`<td><button class="btn secondary delete-transaction" data-id="${Number(t.id)}" aria-label="Delete ${escapeHtml(t.merchant)}">Delete</button></td>`:''}</tr>`).join('') || `<tr><td colspan="${showActions?6:5}" class="empty">No transactions yet. Add your first transaction.</td></tr>`;
 if(window.lucide)lucide.createIcons();
}
function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function renderDashboard(){
 const t=dashboard||{};
 if($('#total-balance'))$('#total-balance').textContent=money(t.balance);
 if($('#total-income'))$('#total-income').textContent=money(t.income);
 if($('#total-expenses'))$('#total-expenses').textContent=money(t.expense);
 if($('#savings-rate'))$('#savings-rate').textContent=`${Number(t.rate||0).toFixed(1).replace(/\.0$/,'')}%`;
 renderTable($('#recent-rows'),transactions,5);
 const categories=t.by_category||[],labels=categories.map(x=>x.category),values=categories.map(x=>x.amount);
 const palette=['#caff32','#45d6a0','#79a9ff','#ffb454','#b99aff','#ff7185','#55c5d8','#a4b0bd'];
 if(window.Chart&&$('#category-chart')){
  if(categoryChart)categoryChart.destroy();
  categoryChart=new Chart($('#category-chart'),{type:'doughnut',data:{labels,datasets:[{data:values,backgroundColor:palette,borderColor:'#101624',borderWidth:4,hoverOffset:5}]},options:{cutout:'72%',maintainAspectRatio:false,plugins:{legend:{display:false}}}});
  const leg=$('#category-legend');if(leg)leg.innerHTML=categories.map((x,i)=>`<div class="legend-item"><span class="dot" style="background:${palette[i%palette.length]}"></span>${escapeHtml(x.category)}<strong>${t.expense?Math.round(x.amount/t.expense*100):0}%</strong></div>`).join('');
 }
 if(window.Chart&&$('#spending-chart')){
  if(cashflowChart)cashflowChart.destroy();
  const monthly=t.monthly||[];
  cashflowChart=new Chart($('#spending-chart'),{type:'line',data:{labels:monthly.map(x=>x.month),datasets:[{label:'Income',data:monthly.map(x=>x.income),borderColor:'#caff32',backgroundColor:'#caff3214',fill:true,tension:.35,borderWidth:2,pointRadius:3},{label:'Expenses',data:monthly.map(x=>x.expense),borderColor:'#45d6a0',backgroundColor:'#45d6a010',fill:true,tension:.35,borderWidth:2,pointRadius:3}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:'#aab5c5',usePointStyle:true,boxWidth:7,font:{size:10}}}},scales:{x:{grid:{display:false},ticks:{color:'#758197',font:{size:9}}},y:{beginAtZero:true,grid:{color:'#ffffff0b'},ticks:{color:'#758197',font:{size:9},callback:v=>'₹'+(v/1000)+'k'}}}}});
 }
 const insights=$$('.ai-insights .insight p');
 if(insights[0])insights[0].textContent=categories.length?`${categories[0].category} is currently your largest recorded expense category at ${money(categories[0].amount)}.`:'Add a few expenses to see your spending pattern.';
 if(insights[1])insights[1].textContent=`Your recorded savings rate is ${Number(t.rate||0).toFixed(1)}%. Review essential bills before setting a regular savings target.`;
 if(insights[2])insights[2].textContent=budgets.filter(b=>b.percent>=80).length?`Review ${budgets.filter(b=>b.percent>=80).map(b=>b.category).join(', ')}; these budgets have reached at least 80%.`:'Your saved category budgets are ready to track as you add transactions.';
}
function renderTransactions(){
 renderTable($('#all-rows'),transactions);
 const filter=$('#ledger-filter');if(filter&&!filter.dataset.bound){filter.dataset.bound='1';filter.addEventListener('input',()=>{$$('#all-rows tr').forEach(r=>r.style.display=r.innerText.toLowerCase().includes(filter.value.toLowerCase())?'':'none')})}
 const exportBtn=$('#export-csv');if(exportBtn&&!exportBtn.dataset.bound){exportBtn.dataset.bound='1';exportBtn.addEventListener('click',()=>{
  const cell=value=>{let text=String(value??'');if(/^\s*[=+\-@]/.test(text))text="'"+text;return `"${text.replaceAll('"','""')}"`};
  const csv=['Date,Description,Category,Type,Amount,Method',...transactions.map(t=>[t.date,t.merchant,t.category,t.type,t.amount,t.method].map(cell).join(','))].join('\n');
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));a.download='gpai-transactions.csv';a.click();URL.revokeObjectURL(a.href);
 })}
 const rows=$('#all-rows');if(rows&&!rows.dataset.bound){rows.dataset.bound='1';rows.addEventListener('click',async event=>{
  const button=event.target.closest('.delete-transaction');
  if(!button||!confirm('Delete this transaction?'))return;
  button.disabled=true;
  try{await api(`/transactions/${button.dataset.id}`,{method:'DELETE'});await refreshData();renderAll();toast('Transaction deleted.')}
  catch(err){button.disabled=false;toast(err.message,true)}
 })}
 const t=dashboard||{};if($('#inflow'))$('#inflow').textContent=money(t.income);if($('#outflow'))$('#outflow').textContent=money(t.expense);if($('#net-flow'))$('#net-flow').textContent=money(t.balance);
}
function renderBudgets(){
 const host=$('#budget-list');if(!host)return;
 const total=budgets.reduce((sum,b)=>sum+Number(b.amount),0),spent=budgets.reduce((sum,b)=>sum+Number(b.spent),0);
 if($('#budget-total'))$('#budget-total').textContent=money(total);
 if($('#budget-spent'))$('#budget-spent').textContent=money(spent);
 if($('#budget-left'))$('#budget-left').textContent=money(total-spent);
 host.innerHTML=budgets.map(b=>{
  const pct=Math.min(100,Math.round(b.percent||0)),state=pct>=90?'danger':pct>=75?'warn':'';
  return `<div class="budget-row"><div class="budget-info"><strong>${escapeHtml(b.category)}</strong><span>${money(b.spent)} / ${money(b.amount)} · ${pct}%</span><button class="btn secondary budget-edit" data-category="${escapeHtml(b.category)}">Edit</button></div><div class="bar ${state}"><span style="width:${pct}%"></span></div></div>`;
 }).join('')||'<p class="card-sub">No budgets saved yet.</p>';
 host.querySelectorAll('.budget-edit').forEach(button=>button.addEventListener('click',()=>openBudgetEditor(button.dataset.category)));
}
function openBudgetEditor(category=''){
 const modal=$('#budget-modal'),categoryInput=$('#budget-category'),amountInput=$('#budget-amount');
 if(!modal||!categoryInput||!amountInput)return;
 categoryInput.value=category||'Food & Dining';
 const current=budgets.find(b=>b.category===category);
 amountInput.value=current?current.amount:'';
 modal.classList.add('open');
 amountInput.focus();
}
function closeBudgetEditor(){
 const modal=$('#budget-modal');if(modal)modal.classList.remove('open');
}
function setupBudgetEditor(){
 const modal=$('#budget-modal'),form=$('#budget-form');
 if(!modal||!form||modal.dataset.bound)return;
 modal.dataset.bound='1';
 const create=$('#create-budget');
 if(create)create.addEventListener('click',()=>openBudgetEditor());
 modal.querySelector('.close-budget-modal').addEventListener('click',closeBudgetEditor);
 modal.addEventListener('click',event=>{if(event.target===modal)closeBudgetEditor()});
 form.addEventListener('submit',async event=>{
  event.preventDefault();
  const submit=form.querySelector('button[type="submit"]'),category=$('#budget-category').value,amount=Number($('#budget-amount').value);
  if(submit){submit.disabled=true;submit.textContent='Saving…'}
  try{
   await api('/budgets',{method:'PUT',body:JSON.stringify({category,amount})});
   await refreshData();renderBudgets();closeBudgetEditor();toast('Budget saved.');
  }catch(err){toast(err.message,true)}
  finally{if(submit){submit.disabled=false;submit.textContent='Save budget'}}
 });
}
function renderAdvisor(){
 if($('#advisor-net-balance'))$('#advisor-net-balance').textContent=money(dashboard?.balance||0);
 const form=$('#chat-form'),input=$('#chat-input'),messages=$('#messages');
 let sending=false;
 async function send(q){
  if(!q.trim()||sending)return;
  sending=true;
  const u=document.createElement('div');u.className='message user';u.textContent=q;messages.appendChild(u);input.value='';
  const pending=document.createElement('div');pending.className='message ai';pending.innerHTML='<small>GP AI · ANALYSING YOUR RECORDS</small>Checking your transactions and budgets…';messages.appendChild(pending);messages.scrollTop=messages.scrollHeight;
  const sendButton=form.querySelector('button[type="submit"]');if(sendButton)sendButton.disabled=true;
  input.disabled=true;
  try{const result=await api('/advisor',{method:'POST',body:JSON.stringify({question:q})});pending.innerHTML=`<small>GP AI · RULE-BASED INSIGHT</small>${escapeHtml(result.answer)}`;}
  catch(err){pending.innerHTML=`<small>GP AI · CONNECTION ERROR</small>${escapeHtml(err.message)}`;}
  finally{sending=false;input.disabled=false;if(sendButton)sendButton.disabled=false;input.focus()}
  messages.scrollTop=messages.scrollHeight;
 }
 if(form)form.addEventListener('submit',e=>{e.preventDefault();send(input.value)});
 $$('.suggestions button').forEach(b=>b.addEventListener('click',()=>send(b.textContent)));
}
async function renderAll(){
 const p=document.body.dataset.page;
 try{if(p==='dashboard')renderDashboard();if(p==='transactions')renderTransactions();if(p==='budgets')renderBudgets();if(p==='advisor')renderAdvisor();}
 catch(err){toast(err.message,true)}
 if(window.lucide)lucide.createIcons();
}
document.addEventListener('DOMContentLoaded',async()=>{
 setupShell();
 try{await refreshData();await renderAll();}
 catch(err){toast(`Could not connect to GP AI backend: ${err.message}`,true);console.error(err)}
});
