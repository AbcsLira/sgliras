// ═══════════════════════════════════════
let finCatsPagar=[], finCatsReceber=[], finFornecedores=[];
let finContasPagar=[], finContasReceber=[];

function finFmt(v){return 'R$ '+(v||0).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2});}
// Data local no formato YYYY-MM-DD (evita bug de timezone do toISOString à noite)
function hojeLocal(){
  const d=new Date();
  return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
}
function dataLocalISO(d){
  return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
}
function finVal(id){return parseFloat(document.getElementById(id)?.value)||0;}
function finStatusBadge(status,venc){
  const hoje=hojeLocal();
  if(status==='pago'||status==='recebido') return `<span class="fin-badge-${status}">${status==='pago'?'Pago':'Recebido'}</span>`;
  if(venc<hoje) return `<span class="fin-badge-vencido">Vencida</span>`;
  return `<span class="fin-badge-aberto">Em aberto</span>`;
}
function finIsVencido(status,venc){
  return (status==='aberto'||status==='pendente')&&venc<hojeLocal();
}

// ── Fechamento Diário ────────────────────────────────────────────────────────
function finIniciarFechamento(){
  // Usa horário local (não UTC) para evitar data errada à noite
  const hoje=new Date();
  const dataLocal=hoje.getFullYear()+'-'+String(hoje.getMonth()+1).padStart(2,'0')+'-'+String(hoje.getDate()).padStart(2,'0');
  document.getElementById('fin-data').value=dataLocal;
  finLimparFormFechamento();
  finCarregarHistorico();
  finCarregarMetaInfo();
}

async function finCarregarMetaResumo(mes){
  const d=await fetch(`/api/fin/meta-mensal?mes=${mes}`).then(r=>r.json());
  document.getElementById('fin-meta-input').value=d.meta_valor||'';
  const progresso=document.getElementById('fin-meta-progresso');
  if(!d.meta_valor){
    progresso.classList.add('hidden');
    return;
  }
  progresso.classList.remove('hidden');
  const pct=Math.min(d.percentual,100);
  document.getElementById('fin-meta-resumo-barra').style.width=pct+'%';
  document.getElementById('fin-meta-resumo-pct').textContent=`${d.percentual}%`;
  document.getElementById('fin-meta-resumo-texto').textContent=
    `${finFmt(d.realizado)} de ${finFmt(d.meta_valor)}`;
  const restantesTexto=d.falta>0
    ? `Faltam ${finFmt(d.falta)} para a meta · média diária atual: ${finFmt(d.media_diaria)}`
    : `Meta atingida · média diária: ${finFmt(d.media_diaria)}`;
  document.getElementById('fin-meta-resumo-media').textContent=restantesTexto;
}

async function finSalvarMeta(){
  const mes=document.getElementById('fin-resumo-mes').value;
  const valor=parseFloat(document.getElementById('fin-meta-input').value);
  if(!mes){toast('Selecione um mês primeiro','var(--danger)');return;}
  if(!valor||valor<=0){toast('Informe um valor de meta válido','var(--danger)');return;}
  const r=await fetch('/api/fin/meta-mensal',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({mes,meta_valor:valor})});
  const d=await r.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast('Meta salva!');
  finCarregarMetaResumo(mes);
}

async function finCarregarMetaInfo(){
  // Termômetro discreto e informativo no fechamento diário (somente admin vê)
  try{
    const mes=hojeLocal().slice(0,7);
    const d=await fetch(`/api/fin/meta-mensal?mes=${mes}`).then(r=>r.json());
    const wrap=document.getElementById('fin-meta-info');
    if(!d.meta_valor){ wrap.classList.add('hidden'); return; }
    wrap.classList.remove('hidden');
    const pct=Math.min(d.percentual,100);
    document.getElementById('fin-meta-barra').style.width=pct+'%';
    document.getElementById('fin-meta-texto').textContent=
      `Venda do mês: ${finFmt(d.realizado)} de ${finFmt(d.meta_valor)} (${d.percentual}%) · média diária: ${finFmt(d.media_diaria)}`;
  }catch(e){
    document.getElementById('fin-meta-info').classList.add('hidden');
  }
}

function finLimparFormFechamento(){
  ['fin-credito','fin-debito','fin-voucher','fin-pix','fin-dinheiro',
   'fin-delivery-qtd','fin-delivery-val','fin-frete','fin-paes-qtd',
   'fin-janta','fin-func-val','fin-cortesia'].forEach(id=>{
    const el=document.getElementById(id);
    if(el) el.value='';
  });
  document.getElementById('fin-obs').value='';
  finAtualizarTotais();
}

function finAtualizarTotais(){
  const credito=finVal('fin-credito'), debito=finVal('fin-debito');
  const voucher=finVal('fin-voucher'), pix=finVal('fin-pix');
  const dinheiro=finVal('fin-dinheiro');
  const cartao=credito+debito+voucher;
  const total=cartao+pix+dinheiro;
  document.getElementById('fin-total-geral').textContent=finFmt(total);
  document.getElementById('fin-total-cartao').textContent=finFmt(cartao);
  document.getElementById('fin-total-pix').textContent=finFmt(pix);
  document.getElementById('fin-total-dinheiro').textContent=finFmt(dinheiro);
}

async function finCarregarDia(){
  const data=document.getElementById('fin-data').value;
  if(!data){toast('Selecione uma data','var(--danger)');return;}
  const d=await fetch(`/api/fin/fechamento/${data}`).then(r=>r.json());
  if(!d.id){finLimparFormFechamento();toast('Nenhum fechamento encontrado para essa data','var(--warn)');return;}
  const campos=['credito','debito','voucher','pix','dinheiro','delivery_val','frete','paes_qtd','janta','func_val','cortesia'];
  campos.forEach(c=>{
    const el=document.getElementById('fin-'+c.replace(/_/g,'-'));
    if(el) el.value=d[c]||'';
  });
  document.getElementById('fin-delivery-qtd').value=d.delivery_qtd||'';
  document.getElementById('fin-obs').value=d.observacao||'';
  finAtualizarTotais();
  toast('Fechamento carregado');
}

async function finSalvarFechamento(){
  const data=document.getElementById('fin-data').value;
  if(!data){toast('Selecione uma data','var(--danger)');return;}
  const payload={
    data,
    credito:finVal('fin-credito'), debito:finVal('fin-debito'),
    voucher:finVal('fin-voucher'), pix:finVal('fin-pix'),
    dinheiro:finVal('fin-dinheiro'),
    delivery_qtd:parseInt(document.getElementById('fin-delivery-qtd').value)||0,
    delivery_val:finVal('fin-delivery-val'),
    frete:finVal('fin-frete'),
    paes_qtd:parseInt(document.getElementById('fin-paes-qtd').value)||0,
    janta:finVal('fin-janta'),
    func_val:finVal('fin-func-val'),
    cortesia:finVal('fin-cortesia'),
    observacao:document.getElementById('fin-obs').value
  };
  const r=await fetch('/api/fin/fechamento',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  if(!r.ok){
    const d=await r.json().catch(()=>({}));
    toast(d.erro||`Erro ao salvar (${r.status})`,'var(--danger)');
    return;
  }
  const d=await r.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast('Fechamento salvo com sucesso!');
  finCarregarHistorico();
  finCarregarMetaInfo();
}

async function finCarregarHistorico(){
  const tbody=document.getElementById('t-fin-historico');
  tbody.innerHTML='<tr><td colspan="9" class="empty">Carregando...</td></tr>';
  // Filtra pelo mês atual para não mostrar fechamentos de meses anteriores
  const hoje=new Date();
  const mesAtual=hoje.getFullYear()+'-'+String(hoje.getMonth()+1).padStart(2,'0');
  const rows=await fetch(`/api/fin/fechamento?mes=${mesAtual}`).then(r=>r.json());
  if(!rows.length){tbody.innerHTML='<tr><td colspan="9" class="empty">Nenhum fechamento registrado neste mês.</td></tr>';return;}
  tbody.innerHTML=rows.slice(0,5).map(r=>{
    const total=r.credito+r.debito+r.voucher+r.pix+r.dinheiro;
    const data=new Date(r.data+'T12:00:00').toLocaleDateString('pt-BR');
    return `<tr>
      <td style="white-space:nowrap">${data}</td>
      <td>${finFmt(r.credito)}</td><td>${finFmt(r.debito)}</td>
      <td>${finFmt(r.voucher)}</td><td>${finFmt(r.pix)}</td>
      <td>${finFmt(r.dinheiro)}</td><td>${finFmt(r.delivery_val)}</td>
      <td style="font-weight:700;color:var(--accent2)">${finFmt(total)}</td>
      <td><button class="btn btn-ghost btn-xs" onclick="finEditarDia('${r.data}')">✏️</button>
          <button class="btn btn-danger btn-xs" onclick="finDeletarDia('${r.data}')">🗑️</button></td>
    </tr>`;
  }).join('');
}

function finEditarDia(data){
  document.getElementById('fin-data').value=data;
  finCarregarDia();
  window.scrollTo({top:0,behavior:'smooth'});
}

async function finDeletarDia(data){
  if(!confirm(`Excluir fechamento de ${new Date(data+'T12:00:00').toLocaleDateString('pt-BR')}?`)) return;
  await fetch(`/api/fin/fechamento/${data}`,{method:'DELETE'});
  toast('Fechamento excluído');
  finCarregarHistorico();
}
