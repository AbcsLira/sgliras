// ═══════════════════════════════════════
// MASSAS DE PIZZA
// ═══════════════════════════════════════
let massaPrecos=[], massaEntregas=[], massaSelecionados=new Set();

function massaIniciar(){
  const mes=hojeLocal().slice(0,7);
  document.getElementById('massa-mes').value=mes;
  const hoje=new Date();
  const dataLocal=hoje.getFullYear()+'-'+String(hoje.getMonth()+1).padStart(2,'0')+'-'+String(hoje.getDate()).padStart(2,'0');
  document.getElementById('massa-ent-data').value=dataLocal;
  document.getElementById('massa-vigencia').value=dataLocal;
  massaCarregarPrecos();
  massaCarregarEntregas();
  massaCarregarPagamentos();
}

async function massaCarregarPrecos(){
  massaPrecos=await fetch('/api/fin/massa-precos').then(r=>r.json());
  const tbody=document.getElementById('t-massa-precos');
  if(!massaPrecos.length){
    tbody.innerHTML='<tr><td colspan="7" class="empty">Nenhum preço cadastrado ainda.</td></tr>';
    return;
  }
  tbody.innerHTML=massaPrecos.map((p,i)=>`<tr>
    <td>${new Date(p.vigente_de+'T12:00:00').toLocaleDateString('pt-BR')}${i===0?' <span class="badge badge-ok" style="font-size:10px">atual</span>':''}</td>
    <td>${finFmt(p.preco_p)}</td>
    <td>${finFmt(p.preco_m)}</td>
    <td>${finFmt(p.preco_g)}</td>
    <td>${finFmt(p.preco_gg)}</td>
    <td>${finFmt(p.preco_burg)}</td>
    <td><button class="btn btn-danger btn-xs" onclick="massaDeletarPreco('${p.vigente_de}')">🗑️</button></td>
  </tr>`).join('');
}

async function massaSalvarPreco(){
  const vigente_de=document.getElementById('massa-vigencia').value;
  const preco_p=parseFloat(document.getElementById('massa-preco-p').value)||0;
  const preco_m=parseFloat(document.getElementById('massa-preco-m').value)||0;
  const preco_g=parseFloat(document.getElementById('massa-preco-g').value)||0;
  const preco_gg=parseFloat(document.getElementById('massa-preco-gg').value)||0;
  const preco_burg=parseFloat(document.getElementById('massa-preco-burg').value)||0;
  if(!vigente_de){toast('Informe a data de vigência','var(--danger)');return;}
  if(!preco_p&&!preco_m&&!preco_g&&!preco_gg&&!preco_burg){toast('Informe ao menos um preço','var(--danger)');return;}
  const r=await fetch('/api/fin/massa-precos',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({vigente_de,preco_p,preco_m,preco_g,preco_gg,preco_burg})});
  const d=await r.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast('Preço salvo!');
  ['massa-preco-p','massa-preco-m','massa-preco-g','massa-preco-gg','massa-preco-burg'].forEach(id=>document.getElementById(id).value='');
  massaCarregarPrecos();
  massaCarregarEntregas();
}

async function massaDeletarPreco(data){
  if(!confirm('Excluir este preço?')) return;
  await fetch(`/api/fin/massa-precos/${data}`,{method:'DELETE'});
  toast('Preço removido');
  massaCarregarPrecos();
}

function massaPrecoVigente(data){
  for(const p of massaPrecos){
    if(p.vigente_de<=data) return p;
  }
  return null;
}

function massaCalcTotal(){
  const data=document.getElementById('massa-ent-data').value||hojeLocal().slice(0,7)+'-01';
  const p=massaPrecoVigente(data);
  if(!p){document.getElementById('massa-calc-preview').textContent='';return;}
  const qtdP=parseInt(document.getElementById('massa-ent-p').value)||0;
  const qtdM=parseInt(document.getElementById('massa-ent-m').value)||0;
  const qtdG=parseInt(document.getElementById('massa-ent-g').value)||0;
  const qtdGG=parseInt(document.getElementById('massa-ent-gg').value)||0;
  const qtdBurg=parseInt(document.getElementById('massa-ent-burg').value)||0;
  const total=qtdP*p.preco_p+qtdM*p.preco_m+qtdG*p.preco_g+qtdGG*p.preco_gg+qtdBurg*p.preco_burg;
  const partes=[];
  if(qtdP) partes.push(`${qtdP}P×${finFmt(p.preco_p)}`);
  if(qtdM) partes.push(`${qtdM}M×${finFmt(p.preco_m)}`);
  if(qtdG) partes.push(`${qtdG}G×${finFmt(p.preco_g)}`);
  if(qtdGG) partes.push(`${qtdGG}GG×${finFmt(p.preco_gg)}`);
  if(qtdBurg) partes.push(`${qtdBurg}Burg×${finFmt(p.preco_burg)}`);
  const preview=document.getElementById('massa-calc-preview');
  if(total>0){
    preview.innerHTML=`<span style="color:var(--accent2);font-weight:600">Valor calculado: ${finFmt(total)}</span> <span style="color:var(--muted)">(${partes.join(' + ')})</span>`;
    document.getElementById('massa-ent-valor').value=total.toFixed(2);
  } else {
    preview.textContent='';
  }
}

async function massaRegistrarEntrega(){
  const data=document.getElementById('massa-ent-data').value;
  if(!data){toast('Informe a data','var(--danger)');return;}
  const qtdP=parseInt(document.getElementById('massa-ent-p').value)||0;
  const qtdM=parseInt(document.getElementById('massa-ent-m').value)||0;
  const qtdG=parseInt(document.getElementById('massa-ent-g').value)||0;
  const qtdGG=parseInt(document.getElementById('massa-ent-gg').value)||0;
  const qtdBurg=parseInt(document.getElementById('massa-ent-burg').value)||0;
  if(!qtdP&&!qtdM&&!qtdG&&!qtdGG&&!qtdBurg){toast('Informe ao menos uma quantidade','var(--danger)');return;}
  const valor=parseFloat(document.getElementById('massa-ent-valor').value)||0;
  const r=await fetch('/api/fin/massa-entregas',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({data,qtd_p:qtdP,qtd_m:qtdM,qtd_g:qtdG,qtd_gg:qtdGG,qtd_burg:qtdBurg,
      valor_total:valor,observacao:document.getElementById('massa-ent-obs').value})});
  const d=await r.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast('Entrega registrada!');
  ['massa-ent-p','massa-ent-m','massa-ent-g','massa-ent-gg','massa-ent-burg','massa-ent-valor','massa-ent-obs'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('massa-calc-preview').textContent='';
  massaCarregarEntregas();
}

async function massaCarregarEntregas(){
  const mes=document.getElementById('massa-mes').value;
  if(!mes) return;
  massaSelecionados=new Set();
  massaAtualizarResumoSel();
  const url=`/api/fin/massa-entregas${mes?`?mes=${mes}`:''}`;
  massaEntregas=await fetch(url).then(r=>r.json());
  const tbody=document.getElementById('t-massa-entregas');
  if(!massaEntregas.length){
    tbody.innerHTML='<tr><td colspan="11" class="empty">Nenhuma entrega neste mês.</td></tr>';
    return;
  }
  tbody.innerHTML=massaEntregas.map(e=>{
    const total=e.qtd_p+e.qtd_m+e.qtd_g+e.qtd_gg+e.qtd_burg;
    const data=new Date(e.data+'T12:00:00').toLocaleDateString('pt-BR');
    const pago=e.pago===1;
    return `<tr style="${pago?'opacity:.55':''}">
      <td><input type="checkbox" class="massa-check" data-id="${e.id}" ${pago?'disabled':''}
          onchange="massaToggleEntrega(${e.id},this.checked)"></td>
      <td style="white-space:nowrap">${data}</td>
      <td>${e.qtd_gg||'—'}</td><td>${e.qtd_g||'—'}</td><td>${e.qtd_m||'—'}</td>
      <td>${e.qtd_p||'—'}</td><td>${e.qtd_burg||'—'}</td>
      <td style="font-weight:600">${total}</td>
      <td style="font-weight:700;color:${pago?'var(--muted)':'var(--accent2)'}">${finFmt(e.valor_total)}</td>
      <td>${pago?'<span class="fin-badge-pago">Pago</span>':'<span class="fin-badge-aberto">Pendente</span>'}</td>
      <td>${!pago?`<button class="btn btn-danger btn-xs" onclick="massaDeletarEntrega(${e.id})">🗑️</button>`:'—'}</td>
    </tr>`;
  }).join('');
}

function massaToggleEntrega(id,checked){
  if(checked) massaSelecionados.add(id);
  else massaSelecionados.delete(id);
  massaAtualizarResumoSel();
}

function massaToggleAll(checked){
  document.querySelectorAll('.massa-check:not([disabled])').forEach(cb=>{
    cb.checked=checked;
    const id=parseInt(cb.dataset.id);
    if(checked) massaSelecionados.add(id);
    else massaSelecionados.delete(id);
  });
  massaAtualizarResumoSel();
}

function massaAtualizarResumoSel(){
  const btn=document.getElementById('btn-massa-pagar');
  const btnLancar=document.getElementById('btn-massa-lancar');
  const resumo=document.getElementById('massa-resumo-sel');
  const info=document.getElementById('massa-sel-info');
  if(!massaSelecionados.size){
    btn.disabled=true;
    if(btnLancar) btnLancar.disabled=true;
    resumo.classList.add('hidden');
    info.textContent='Nenhuma entrega selecionada'; return;
  }
  const selecionadas=massaEntregas.filter(e=>massaSelecionados.has(e.id));
  const totalVal=selecionadas.reduce((s,e)=>s+e.valor_total,0);
  btn.disabled=false;
  if(btnLancar) btnLancar.disabled=false;
  resumo.classList.remove('hidden');
  info.textContent=`${massaSelecionados.size} entrega(s) selecionada(s)`;
  document.getElementById('massa-resumo-valor').textContent=finFmt(totalVal);
  document.getElementById('massa-resumo-detalhe').textContent=`${massaSelecionados.size} entrega(s)`;
}

function massaLancarContasPagar(){
  // Massas já são lançadas automaticamente ao registrar a entrega
  toast('As entregas de massa já são lançadas em Contas a Pagar automaticamente ao registrar. Use "Pagar selecionadas" para quitá-las.','var(--accent)');
}

async function massaGerarPagamento(){
  if(!massaSelecionados.size){toast('Selecione ao menos uma entrega','var(--danger)');return;}
  const selecionadas=massaEntregas.filter(e=>massaSelecionados.has(e.id));
  const totalVal=selecionadas.reduce((s,e)=>s+e.valor_total,0);
  if(!confirm(`Marcar ${selecionadas.length} entrega(s) como pagas? Total: ${finFmt(totalVal)}`)) return;
  const r=await fetch('/api/fin/massa-pagamento',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({ids:Array.from(massaSelecionados)})});
  const d=await r.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast(`Pagamento registrado! ${finFmt(d.valor_total)} ✅`);
  massaSelecionados=new Set();
  massaCarregarEntregas();
  massaCarregarPagamentos();
}

async function massaDeletarEntrega(id){
  if(!confirm('Excluir esta entrega?')) return;
  await fetch(`/api/fin/massa-entregas/${id}`,{method:'DELETE'});
  toast('Entrega excluída');
  massaCarregarEntregas();
}

async function massaCarregarPagamentos(){
  const rows=await fetch('/api/fin/contas-pagar?status=pago').then(r=>r.json())
    .then(r=>r.filter(c=>c.categoria==='Fornecedor'&&c.descricao.startsWith('Massas')));
  const tbody=document.getElementById('t-massa-pagamentos');
  if(!rows.length){tbody.innerHTML='<tr><td colspan="3" class="empty">Nenhum pagamento registrado.</td></tr>';return;}
  tbody.innerHTML=rows.map(p=>`<tr>
    <td style="white-space:nowrap">${new Date(p.pago_em).toLocaleDateString('pt-BR',{day:'2-digit',month:'2-digit',year:'numeric'})}</td>
    <td style="font-size:12px;color:var(--muted)">${p.descricao}</td>
    <td style="font-weight:700;color:var(--accent2)">${finFmt(p.valor)}</td>
  </tr>`).join('');
}
