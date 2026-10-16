// ═══════════════════════════════════════
// RELATÓRIO DE PÃES
// ═══════════════════════════════════════
let paesDias=[], paesPrecos=[], paesSelecionados=new Set();

function paesIniciar(){
  const mes=hojeLocal().slice(0,7);
  document.getElementById('paes-mes').value=mes;
  document.getElementById('paes-nova-vigencia').value=hojeLocal();
  paesCarregarPrecos();
  paesCarregarRelatorio();
  paesCarregarPagamentos();
}

async function paesCarregarPrecos(){
  paesPrecos=await fetch('/api/fin/preco-pao').then(r=>r.json());
  const tbody=document.getElementById('t-paes-precos');
  if(!paesPrecos.length){
    tbody.innerHTML='<tr><td colspan="3" class="empty">Nenhum preço cadastrado ainda.</td></tr>';
    return;
  }
  tbody.innerHTML=paesPrecos.map((p,i)=>`<tr>
    <td>${new Date(p.vigente_de+'T12:00:00').toLocaleDateString('pt-BR')}${i===0?' <span class="badge badge-ok" style="font-size:10px">atual</span>':''}</td>
    <td style="font-weight:600">${finFmt(p.preco)}</td>
    <td><button class="btn btn-danger btn-xs" onclick="paesdeletarPreco('${p.vigente_de}')">🗑️</button></td>
  </tr>`).join('');
}

async function paesSalvarPreco(){
  const preco=parseFloat(document.getElementById('paes-novo-preco').value);
  const vigente_de=document.getElementById('paes-nova-vigencia').value;
  if(!preco||!vigente_de){toast('Preencha preço e data de vigência','var(--danger)');return;}
  const r=await fetch('/api/fin/preco-pao',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({preco,vigente_de})});
  const d=await r.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast('Preço salvo!');
  document.getElementById('paes-novo-preco').value='';
  paesCarregarPrecos();
  paesCarregarRelatorio();
}

async function paesdeletarPreco(data){
  if(!confirm('Excluir este preço?')) return;
  await fetch(`/api/fin/preco-pao/${data}`,{method:'DELETE'});
  toast('Preço removido');
  paesCarregarPrecos();
  paesCarregarRelatorio();
}

async function paesCarregarRelatorio(){
  const mes=document.getElementById('paes-mes').value;
  if(!mes) return;
  paesSelecionados=new Set();
  paesAtualizarResumoSelecao();
  const tbody=document.getElementById('t-paes-relatorio');
  tbody.innerHTML='<tr><td colspan="7" class="empty">Carregando...</td></tr>';
  paesDias=await fetch(`/api/fin/relatorio-paes?mes=${mes}`).then(r=>r.json());
  if(!paesDias.length){
    tbody.innerHTML='<tr><td colspan="7" class="empty">Nenhum fechamento com pães neste mês.</td></tr>';
    return;
  }
  const DIAS=['Dom','Seg','Ter','Qua','Qui','Sex','Sáb'];
  tbody.innerHTML=paesDias.map(d=>{
    const dt=new Date(d.data+'T12:00:00');
    const diaSemana=DIAS[dt.getDay()];
    const pago=d.pago;
    return `<tr style="${pago?'opacity:.55':''}">
      <td><input type="checkbox" class="paes-check" data-data="${d.data}"
          ${pago?'disabled':''}
          onchange="paesToggleDia('${d.data}',this.checked)"></td>
      <td style="white-space:nowrap">${dt.toLocaleDateString('pt-BR')}</td>
      <td style="color:var(--muted)">${diaSemana}</td>
      <td style="font-weight:600">${d.paes_qtd.toLocaleString('pt-BR')}</td>
      <td style="color:var(--muted)">${d.preco>0?finFmt(d.preco):'<span style="color:var(--danger)">sem preço</span>'}</td>
      <td style="font-weight:700;color:${d.valor>0?'var(--accent2)':'var(--muted)'}">${finFmt(d.valor)}</td>
      <td>${pago?'<span class="fin-badge-pago">Pago</span>':'<span class="fin-badge-aberto">Pendente</span>'}</td>
    </tr>`;
  }).join('');
}

function paesToggleDia(data,checked){
  if(checked) paesSelecionados.add(data);
  else paesSelecionados.delete(data);
  paesAtualizarResumoSelecao();
}

function paesToggleAll(checked){
  document.querySelectorAll('.paes-check:not([disabled])').forEach(cb=>{
    cb.checked=checked;
    const dt=cb.dataset.data;
    if(checked) paesSelecionados.add(dt);
    else paesSelecionados.delete(dt);
  });
  paesAtualizarResumoSelecao();
}

function paesAtualizarResumoSelecao(){
  const btn=document.getElementById('btn-paes-pagar');
  const btnLancar=document.getElementById('btn-paes-lancar');
  const resumo=document.getElementById('paes-resumo-selecao');
  const info=document.getElementById('paes-selecionados-info');
  if(!paesSelecionados.size){
    btn.disabled=true;
    if(btnLancar) btnLancar.disabled=true;
    resumo.classList.add('hidden');
    info.textContent='Nenhum dia selecionado';
    return;
  }
  const selecionados=paesDias.filter(d=>paesSelecionados.has(d.data));
  const totalQtd=selecionados.reduce((s,d)=>s+d.paes_qtd,0);
  const totalVal=selecionados.reduce((s,d)=>s+d.valor,0);
  btn.disabled=false;
  if(btnLancar) btnLancar.disabled=false;
  resumo.classList.remove('hidden');
  info.textContent=`${paesSelecionados.size} dia(s) · ${totalQtd.toLocaleString('pt-BR')} pães`;
  document.getElementById('paes-resumo-valor').textContent=finFmt(totalVal);
  document.getElementById('paes-resumo-detalhe').textContent=
    `${paesSelecionados.size} dia(s) selecionado(s) · ${totalQtd.toLocaleString('pt-BR')} pães`;
}

async function paesLancarContasPagar(){
  if(!paesSelecionados.size){toast('Selecione ao menos um dia','var(--danger)');return;}
  const selecionados=paesDias.filter(d=>paesSelecionados.has(d.data)&&!d.pago);
  const semPreco=selecionados.filter(d=>d.preco===0);
  if(semPreco.length){toast(`${semPreco.length} dia(s) sem preço cadastrado`,'var(--danger)');return;}
  const dias=selecionados.map(d=>({data:d.data,valor:d.valor,preco:d.preco,paes_qtd:d.paes_qtd}));
  const r=await fetch('/api/fin/paes-lancar-contas',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({dias})});
  const d=await r.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast(`${d.criadas} conta(s) lançada(s) em Contas a Pagar! 📋`);
}

async function paesGerarPagamento(){
  if(!paesSelecionados.size){toast('Selecione ao menos um dia','var(--danger)');return;}
  const selecionados=paesDias.filter(d=>paesSelecionados.has(d.data));
  const semPreco=selecionados.filter(d=>d.preco===0);
  if(semPreco.length){
    toast(`${semPreco.length} dia(s) sem preço cadastrado — cadastre o preço primeiro`,'var(--danger)');
    return;
  }
  const totalVal=selecionados.reduce((s,d)=>s+d.valor,0);
  const datas=Array.from(paesSelecionados);
  if(!confirm(`Marcar ${datas.length} dia(s) como pagos? Total: ${finFmt(totalVal)}`)) return;
  const r=await fetch('/api/fin/paes-pagamento',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({datas,valor:totalVal})});
  const d=await r.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast('Pagamento registrado com sucesso! ✅');
  paesSelecionados=new Set();
  paesCarregarRelatorio();
  paesCarregarPagamentos();
}

async function paesDesfazerPagamento(id){
  if(!confirm('Desfazer este pagamento? As datas voltarão a aparecer como pendentes.')) return;
  const r=await fetch(`/api/fin/paes-pagamento/${id}`,{method:'DELETE'});
  const d=await r.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast(`Pagamento desfeito! ${d.datas_liberadas.length} dia(s) liberado(s).`);
  paesCarregarRelatorio();
  paesCarregarPagamentos();
}

async function paesCarregarPagamentos(){
  const tbody=document.getElementById('t-paes-pagamentos');
  const rows=await fetch('/api/fin/contas-pagar?status=pago').then(r=>r.json())
    .then(r=>r.filter(c=>c.categoria==='Fornecedor'&&c.descricao.startsWith('Pães')));
  // Buscar também do histórico de pagamentos para ter o id e botão de desfazer
  const pagamentos=await fetch('/api/fin/relatorio-paes').then(r=>r.json()).catch(()=>[]);
  const histPag=await fetch('/api/fin/paes-historico-pagamentos').then(r=>r.json()).catch(()=>[]);
  if(!histPag.length&&!rows.length){tbody.innerHTML='<tr><td colspan="4" class="empty">Nenhum pagamento registrado.</td></tr>';return;}
  // Usar histPag se disponível, senão rows
  const fonte=histPag.length?histPag:rows;
  tbody.innerHTML=fonte.map(p=>`<tr>
    <td style="white-space:nowrap">${new Date(p.pago_em).toLocaleDateString('pt-BR',{day:'2-digit',month:'2-digit',year:'numeric'})}</td>
    <td style="font-size:12px;color:var(--muted)">${p.descricao}</td>
    <td style="font-weight:700;color:var(--accent2)">${finFmt(p.valor)}</td>
    <td><button class="btn btn-danger btn-xs" onclick="paesDesfazerPagamento(${p.id})" title="Desfazer este pagamento">↩️</button></td>
  </tr>`).join('');
}
