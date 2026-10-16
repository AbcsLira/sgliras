// ── Contas a Pagar ────────────────────────────────────────────────────────────
let finFiltroStatusPagar='todos';

async function finCarregarContasPagar(){
  if(!finCatsPagar.length) finCatsPagar=await fetch('/api/fin/categorias-pagar').then(r=>r.json());
  if(!finFornecedores.length) finFornecedores=await fetch('/api/fornecedores').then(r=>r.json());

  // Salvar valores selecionados ANTES de reconstruir os selects
  const selCat=document.getElementById('fin-filtro-cat-pagar');
  const catValorAtual=selCat.value;
  selCat.innerHTML='<option value="">Todas</option>';
  finCatsPagar.forEach(c=>selCat.add(new Option(c.nome,c.nome)));
  // Restaurar seleção após reconstruir
  if(catValorAtual) selCat.value=catValorAtual;

  const selForn=document.getElementById('fin-filtro-forn-pagar');
  if(selForn.options.length<=1){
    finFornecedores.forEach(f=>selForn.add(new Option(f.nome,f.id)));
  }

  finCarregarAlertasVencimento();

  // Montar URL com filtros
  const params=new URLSearchParams();
  if(finFiltroStatusPagar!=='todos'&&finFiltroStatusPagar!=='vencido')
    params.set('status',finFiltroStatusPagar);
  else if(finFiltroStatusPagar==='vencido')
    params.set('status','aberto');
  const catFiltro=document.getElementById('fin-filtro-cat-pagar').value;
  const mesFiltro=document.getElementById('fin-filtro-mes-pagar').value;
  const fornFiltro=document.getElementById('fin-filtro-forn-pagar').value;
  if(catFiltro) params.set('categoria',catFiltro);
  if(mesFiltro) params.set('mes',mesFiltro);
  if(fornFiltro) params.set('fornecedor_id',fornFiltro);

  finContasPagar=await fetch(`/api/fin/contas-pagar?${params}`).then(r=>r.json());
  if(finFiltroStatusPagar==='vencido'){
    const hoje=hojeLocal();
    finContasPagar=finContasPagar.filter(c=>c.vencimento<hoje&&c.status==='aberto');
  }
  finRenderContasPagar();
  finAtualizarCardsPagar();
  finCarregarResumoCategorias();
}

function finLimparFiltrosPagar(){
  document.getElementById('fin-filtro-cat-pagar').value='';
  document.getElementById('fin-filtro-mes-pagar').value='';
  document.getElementById('fin-filtro-forn-pagar').value='';
  finFiltroStatusPagar='todos';
  document.querySelectorAll('#page-fin-contas-pagar .filter-chip').forEach((c,i)=>c.classList.toggle('active',i===0));
  finCarregarContasPagar();
}

function finFiltrarPagar(status,el){
  document.querySelectorAll('#page-fin-contas-pagar .filter-chip').forEach(c=>c.classList.remove('active'));
  el.classList.add('active');
  finFiltroStatusPagar=status;
  finCarregarContasPagar();
}

function finRenderContasPagar(){
  const tbody=document.getElementById('t-fin-pagar');
  if(!finContasPagar.length){tbody.innerHTML='<tr><td colspan="8" class="empty">Nenhuma conta encontrada.</td></tr>';return;}
  const hoje=hojeLocal();
  tbody.innerHTML=finContasPagar.map(c=>`<tr>
    <td>${c.descricao}</td>
    <td><span class="badge badge-unit">${c.categoria}</span></td>
    <td>${c.fornecedor_nome||'—'}</td>
    <td style="white-space:nowrap;${c.status==='aberto'&&c.vencimento<hoje?'color:var(--danger)':''}">${new Date(c.vencimento+'T12:00:00').toLocaleDateString('pt-BR')}</td>
    <td style="font-weight:600">${finFmt(c.valor)}</td>
    <td style="font-size:11px;color:var(--muted);max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${c.observacao||''}">${c.observacao||'—'}</td>
    <td>${finStatusBadge(c.status,c.vencimento)}</td>
    <td style="white-space:nowrap">
      ${c.status==='aberto'?`<button class="btn btn-success btn-xs" onclick="finPagarConta(${c.id})">✅</button> `:''}
      <button class="btn btn-ghost btn-xs" onclick="finAbrirEdicaoPagar(${c.id})" title="Editar">✏️</button>
      <button class="btn btn-danger btn-xs" onclick="finDeletarContaPagar(${c.id})">🗑️</button>
    </td>
  </tr>`).join('');
}

async function finCarregarResumoCategorias(){
  const wrap=document.getElementById('fin-resumo-cats-wrap');
  const cont=document.getElementById('fin-resumo-cats');
  const mesFiltro=document.getElementById('fin-filtro-mes-pagar').value;
  if(!mesFiltro){wrap.classList.add('hidden');return;}

  const params=new URLSearchParams();
  params.set('mes',mesFiltro);
  if(finFiltroStatusPagar!=='todos'&&finFiltroStatusPagar!=='vencido')
    params.set('status',finFiltroStatusPagar);

  const cats=await fetch(`/api/fin/contas-pagar/resumo-categorias?${params}`).then(r=>r.json());
  if(!cats.length){wrap.classList.add('hidden');return;}

  wrap.classList.remove('hidden');
  cont.innerHTML=cats.map(c=>`
    <div class="table-wrap" style="padding:10px 14px;min-width:160px">
      <div style="font-size:11px;color:var(--muted);margin-bottom:2px">${c.categoria}</div>
      <div style="font-weight:700;font-size:16px">${finFmt(c.total_valor)}</div>
      <div style="font-size:11px;color:var(--muted)">${c.total_contas} conta(s)</div>
    </div>`).join('');
}

async function finAtualizarCardsPagar(){
  const todas=await fetch('/api/fin/contas-pagar').then(r=>r.json());
  const hoje=hojeLocal();
  const mesFmt=hojeLocal().slice(0,7);
  const aberto=todas.filter(c=>c.status==='aberto').reduce((s,c)=>s+c.valor,0);
  const vencido=todas.filter(c=>c.status==='aberto'&&c.vencimento<hoje).reduce((s,c)=>s+c.valor,0);
  const pago=todas.filter(c=>c.status==='pago'&&(c.pago_em||'').startsWith(mesFmt)).reduce((s,c)=>s+c.valor,0);
  document.getElementById('fin-pagar-total-aberto').textContent=finFmt(aberto);
  document.getElementById('fin-pagar-total-vencido').textContent=finFmt(vencido);
  document.getElementById('fin-pagar-total-pago').textContent=finFmt(pago);
}

async function finAbrirEdicaoPagar(id){
  if(!finCatsPagar.length) finCatsPagar=await fetch('/api/fin/categorias-pagar').then(r=>r.json());
  if(!finFornecedores.length) finFornecedores=await fetch('/api/fornecedores').then(r=>r.json());
  const c=finContasPagar.find(x=>x.id===id);
  if(!c) return;
  document.getElementById('fin-editar-id').value=id;
  document.getElementById('fin-editar-desc').value=c.descricao;
  document.getElementById('fin-editar-valor').value=c.valor;
  document.getElementById('fin-editar-venc').value=c.vencimento;
  document.getElementById('fin-editar-obs').value=c.observacao||'';
  document.getElementById('fin-editar-cat').innerHTML=finCatsPagar.map(cat=>`<option ${cat.nome===c.categoria?'selected':''}>${cat.nome}</option>`).join('');
  document.getElementById('fin-editar-forn').innerHTML=`<option value="">— nenhum —</option>`
    +finFornecedores.map(f=>`<option value="${f.id}" ${f.id===c.fornecedor_id?'selected':''}>${f.nome}</option>`).join('');
  document.getElementById('modal-fin-editar-pagar').classList.remove('hidden');
}

async function finSalvarEdicaoPagar(){
  const id=parseInt(document.getElementById('fin-editar-id').value);
  const desc=document.getElementById('fin-editar-desc').value.trim();
  const valor=parseFloat(document.getElementById('fin-editar-valor').value);
  const venc=document.getElementById('fin-editar-venc').value;
  if(!desc||!valor||!venc){toast('Preencha descrição, valor e vencimento','var(--danger)');return;}
  const r=await fetch(`/api/fin/contas-pagar/${id}`,{method:'PUT',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({
      descricao:desc, valor, vencimento:venc,
      categoria:document.getElementById('fin-editar-cat').value,
      fornecedor_id:document.getElementById('fin-editar-forn').value||null,
      observacao:document.getElementById('fin-editar-obs').value
    })});
  const d=await r.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast('Conta atualizada!');
  fecharModal('modal-fin-editar-pagar');
  finCarregarContasPagar();
}

function finToggleGerenciarCats(){
  const painel=document.getElementById('fin-cats-painel');
  const seta=document.getElementById('fin-cats-seta');
  const aberto=!painel.classList.contains('hidden');
  painel.classList.toggle('hidden');
  seta.textContent=aberto?'▸ expandir':'▾ recolher';
  if(!aberto) finRenderCategorias();
}

function finRenderCategorias(){
  const cont=document.getElementById('t-fin-cats');
  if(!finCatsPagar.length){cont.innerHTML='<span style="color:var(--muted);font-size:12px">Nenhuma categoria cadastrada.</span>';return;}
  cont.innerHTML=finCatsPagar.map(c=>`
    <div style="display:flex;align-items:center;gap:6px;background:rgba(255,255,255,.05);border:1px solid var(--border);border-radius:20px;padding:4px 10px 4px 12px">
      <span id="fin-cat-label-${c.id}" style="font-size:13px">${c.nome}</span>
      <input id="fin-cat-edit-${c.id}" class="fin-input hidden" value="${c.nome}"
        style="width:120px;padding:2px 6px;font-size:12px;border-radius:6px"
        onkeydown="if(event.key==='Enter')finSalvarRenomeacao(${c.id});if(event.key==='Escape')finCancelarRenomeacao(${c.id})">
      <button onclick="finIniciarRenomeacao(${c.id})" title="Renomear"
        style="background:none;border:none;cursor:pointer;color:var(--muted);font-size:12px;padding:0">✏️</button>
      <button onclick="finExcluirCategoria(${c.id},'${c.nome.replace(/'/g,"\\'")}')" title="Excluir"
        style="background:none;border:none;cursor:pointer;color:var(--danger);font-size:12px;padding:0">✕</button>
    </div>`).join('');
}

function finIniciarRenomeacao(id){
  document.getElementById(`fin-cat-label-${id}`).classList.add('hidden');
  document.getElementById(`fin-cat-edit-${id}`).classList.remove('hidden');
  document.getElementById(`fin-cat-edit-${id}`).focus();
  document.getElementById(`fin-cat-edit-${id}`).select();
}

function finCancelarRenomeacao(id){
  document.getElementById(`fin-cat-label-${id}`).classList.remove('hidden');
  document.getElementById(`fin-cat-edit-${id}`).classList.add('hidden');
}

async function finSalvarRenomeacao(id){
  const nome=document.getElementById(`fin-cat-edit-${id}`).value.trim();
  if(!nome){toast('Nome não pode estar vazio','var(--danger)');return;}
  const r=await fetch(`/api/fin/categorias-pagar/${id}`,{method:'PUT',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({nome})});
  const d=await r.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast('Categoria renomeada!');
  finCatsPagar=[];
  finCarregarContasPagar();
  // Reabrir painel após reload
  setTimeout(()=>{
    const painel=document.getElementById('fin-cats-painel');
    if(painel.classList.contains('hidden')) finToggleGerenciarCats();
    else finRenderCategorias();
  },300);
}

async function finCriarCategoria(){
  const nome=document.getElementById('fin-nova-cat-input').value.trim();
  if(!nome){toast('Digite um nome para a categoria','var(--danger)');return;}
  const r=await fetch('/api/fin/categorias-pagar',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({nome})});
  const d=await r.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast('Categoria criada!');
  document.getElementById('fin-nova-cat-input').value='';
  finCatsPagar=[];
  finCarregarContasPagar();
  setTimeout(()=>{
    const painel=document.getElementById('fin-cats-painel');
    if(painel.classList.contains('hidden')) finToggleGerenciarCats();
    else finRenderCategorias();
  },300);
}

async function finExcluirCategoria(id,nome){
  if(!confirm(`Excluir a categoria "${nome}"?\n\nSó é possível excluir categorias sem contas vinculadas.`)) return;
  const r=await fetch(`/api/fin/categorias-pagar/${id}`,{method:'DELETE'});
  const d=await r.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast('Categoria excluída!');
  finCatsPagar=[];
  finCarregarContasPagar();
  setTimeout(()=>finRenderCategorias(),300);
}

async function finAbrirModalPagar(){
  if(!finCatsPagar.length) finCatsPagar=await fetch('/api/fin/categorias-pagar').then(r=>r.json());
  if(!finFornecedores.length) finFornecedores=await fetch('/api/fornecedores').then(r=>r.json());
  document.getElementById('fin-pagar-cat').innerHTML=finCatsPagar.map(c=>`<option>${c.nome}</option>`).join('');
  document.getElementById('fin-pagar-forn').innerHTML=`<option value="">— nenhum —</option>`
    +finFornecedores.map(f=>`<option value="${f.id}">${f.nome}</option>`).join('');
  document.getElementById('fin-pagar-desc').value='';
  document.getElementById('fin-pagar-valor').value='';
  document.getElementById('fin-pagar-venc').value=hojeLocal();
  document.getElementById('fin-pagar-obs').value='';
  document.getElementById('fin-pagar-parcelas').value='1';
  document.getElementById('fin-parcelas-grade').classList.add('hidden');
  document.getElementById('fin-parcelas-grade').innerHTML='';
  document.getElementById('modal-fin-pagar').classList.remove('hidden');
}

function finAtualizarParcelas(){
  const n=parseInt(document.getElementById('fin-pagar-parcelas').value)||1;
  const valorTotal=parseFloat(document.getElementById('fin-pagar-valor').value)||0;
  const vencBase=document.getElementById('fin-pagar-venc').value;
  const grade=document.getElementById('fin-parcelas-grade');

  if(n<=1){
    grade.classList.add('hidden');
    grade.innerHTML='';
    return;
  }

  // Valor de cada parcela (última absorve centavos de arredondamento)
  const valorParcela=Math.floor((valorTotal/n)*100)/100;
  const valorUltima=Math.round((valorTotal-valorParcela*(n-1))*100)/100;

  // Gerar datas: primeira = vencBase, próximas +1 mês cada
  const datas=[];
  for(let i=0;i<n;i++){
    if(i===0){
      datas.push(vencBase);
    } else if(vencBase){
      const d=new Date(vencBase+'T12:00:00');
      d.setMonth(d.getMonth()+i);
      datas.push(dataLocalISO(d));
    } else {
      datas.push('');
    }
  }

  grade.classList.remove('hidden');
  grade.innerHTML=`
    <div style="font-size:11px;color:var(--muted);margin-bottom:8px">
      Ajuste o valor e vencimento de cada parcela se necessário:
    </div>
    <div style="display:grid;grid-template-columns:auto 1fr 1fr;gap:6px 10px;align-items:center;font-size:12px">
      <div style="color:var(--muted);font-weight:600">Parcela</div>
      <div style="color:var(--muted);font-weight:600">Valor (R$)</div>
      <div style="color:var(--muted);font-weight:600">Vencimento</div>
      ${Array.from({length:n},(_,i)=>`
        <div style="color:var(--muted);text-align:center;font-weight:700">${i+1}/${n}</div>
        <input type="number" id="fin-parc-val-${i}" class="fin-input" step="0.01" min="0"
          value="${i===n-1?valorUltima.toFixed(2):valorParcela.toFixed(2)}"
          style="padding:5px 8px;font-size:12px">
        <input type="date" id="fin-parc-venc-${i}" class="fin-input"
          value="${datas[i]}"
          style="padding:5px 8px;font-size:12px">
      `).join('')}
    </div>
    <div id="fin-parcelas-aviso" style="font-size:11px;margin-top:8px;color:var(--muted)">
      Total: ${valorTotal>0?finFmt(valorTotal):'—'}
    </div>`;
}

async function finSalvarContaPagar(){
  const desc=document.getElementById('fin-pagar-desc').value.trim();
  const valorTotal=parseFloat(document.getElementById('fin-pagar-valor').value);
  const venc=document.getElementById('fin-pagar-venc').value;
  const n=parseInt(document.getElementById('fin-pagar-parcelas').value)||1;
  if(!desc||!valorTotal){toast('Preencha descrição e valor','var(--danger)');return;}

  const cat=document.getElementById('fin-pagar-cat').value;
  const forn=document.getElementById('fin-pagar-forn').value||null;
  const obs=document.getElementById('fin-pagar-obs').value;

  if(n<=1){
    // Conta simples — comportamento original
    if(!venc){toast('Preencha o vencimento','var(--danger)');return;}
    const r=await fetch('/api/fin/contas-pagar',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({descricao:desc,valor:valorTotal,vencimento:venc,
        categoria:cat,fornecedor_id:forn,observacao:obs})});
    const d=await r.json();
    if(d.erro){toast(d.erro,'var(--danger)');return;}
    toast('Conta a pagar salva!');
  } else {
    // Parcelado — criar n contas
    let erros=[], sucesso=0;
    for(let i=0;i<n;i++){
      const valorParc=parseFloat(document.getElementById(`fin-parc-val-${i}`).value);
      const vencParc=document.getElementById(`fin-parc-venc-${i}`).value;
      if(!vencParc||!valorParc){
        toast(`Preencha valor e vencimento da parcela ${i+1}/${n}`,'var(--danger)');
        return;
      }
      const descParc=`${desc} ${i+1}/${n}`;
      const r=await fetch('/api/fin/contas-pagar',{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({descricao:descParc,valor:valorParc,vencimento:vencParc,
          categoria:cat,fornecedor_id:forn,
          observacao:obs?`${obs} — parcela ${i+1}/${n}`:`Parcela ${i+1}/${n}`})});
      const d=await r.json();
      if(d.erro) erros.push(d.erro);
      else sucesso++;
    }
    if(erros.length) toast(`${sucesso} parcelas ok, ${erros.length} com erro`,'var(--danger)');
    else toast(`${n} parcelas criadas com sucesso! 💳`);
  }

  fecharModal('modal-fin-pagar');
  finCarregarContasPagar();
}

async function finPagarConta(id){
  if(!confirm('Marcar essa conta como paga?')) return;
  await fetch(`/api/fin/contas-pagar/${id}/pagar`,{method:'POST'});
  toast('Conta marcada como paga');
  finCarregarContasPagar();
}

async function finDeletarContaPagar(id){
  if(!confirm('Excluir essa conta?')) return;
  await fetch(`/api/fin/contas-pagar/${id}`,{method:'DELETE'});
  toast('Conta excluída');
  finCarregarContasPagar();
}

// ── Contas a Receber ──────────────────────────────────────────────────────────
let finFiltroStatusReceber='todos';

async function finCarregarContasReceber(){
  if(!finCatsReceber.length) finCatsReceber=await fetch('/api/fin/categorias-receber').then(r=>r.json());
  const url=finFiltroStatusReceber==='todos'?'/api/fin/contas-receber':`/api/fin/contas-receber?status=${finFiltroStatusReceber==='vencido'?'aberto':finFiltroStatusReceber}`;
  finContasReceber=await fetch(url).then(r=>r.json());
  if(finFiltroStatusReceber==='vencido'){
    const hoje=hojeLocal();
    finContasReceber=finContasReceber.filter(c=>c.vencimento<hoje&&c.status==='aberto');
  }
  finRenderContasReceber();
  finAtualizarCardsReceber();
}

function finFiltrarReceber(status,el){
  document.querySelectorAll('#page-fin-contas-receber .filter-chip').forEach(c=>c.classList.remove('active'));
  el.classList.add('active');
  finFiltroStatusReceber=status;
  finCarregarContasReceber();
}

function finRenderContasReceber(){
  const tbody=document.getElementById('t-fin-receber');
  if(!finContasReceber.length){tbody.innerHTML='<tr><td colspan="6" class="empty">Nenhuma conta encontrada.</td></tr>';return;}
  const hoje=hojeLocal();
  tbody.innerHTML=finContasReceber.map(c=>`<tr>
    <td>${c.descricao}</td>
    <td><span class="badge badge-unit">${c.categoria}</span></td>
    <td style="white-space:nowrap;${c.status==='aberto'&&c.vencimento<hoje?'color:var(--danger)':''}">${new Date(c.vencimento+'T12:00:00').toLocaleDateString('pt-BR')}</td>
    <td style="font-weight:600">${finFmt(c.valor)}</td>
    <td>${finStatusBadge(c.status,c.vencimento)}</td>
    <td style="white-space:nowrap">
      ${c.status==='aberto'?`<button class="btn btn-success btn-xs" onclick="finReceberConta(${c.id})">✅ Receber</button> `:''}
      <button class="btn btn-danger btn-xs" onclick="finDeletarContaReceber(${c.id})">🗑️</button>
    </td>
  </tr>`).join('');
}

async function finAtualizarCardsReceber(){
  const todas=await fetch('/api/fin/contas-receber').then(r=>r.json());
  const mesFmt=hojeLocal().slice(0,7);
  const aberto=todas.filter(c=>c.status==='aberto').reduce((s,c)=>s+c.valor,0);
  const recebido=todas.filter(c=>c.status==='recebido'&&(c.recebido_em||'').startsWith(mesFmt)).reduce((s,c)=>s+c.valor,0);
  document.getElementById('fin-receber-total-aberto').textContent=finFmt(aberto);
  document.getElementById('fin-receber-total-recebido').textContent=finFmt(recebido);
}

async function finAbrirModalReceber(){
  if(!finCatsReceber.length) finCatsReceber=await fetch('/api/fin/categorias-receber').then(r=>r.json());
  document.getElementById('fin-receber-cat').innerHTML=finCatsReceber.map(c=>`<option>${c}</option>`).join('');
  document.getElementById('fin-receber-desc').value='';
  document.getElementById('fin-receber-valor').value='';
  document.getElementById('fin-receber-venc').value=hojeLocal();
  document.getElementById('fin-receber-obs').value='';
  document.getElementById('modal-fin-receber').classList.remove('hidden');
}

async function finSalvarContaReceber(){
  const desc=document.getElementById('fin-receber-desc').value.trim();
  const valor=parseFloat(document.getElementById('fin-receber-valor').value);
  const venc=document.getElementById('fin-receber-venc').value;
  if(!desc||!valor||!venc){toast('Preencha descrição, valor e vencimento','var(--danger)');return;}
  const r=await fetch('/api/fin/contas-receber',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    descricao:desc, valor, vencimento:venc,
    categoria:document.getElementById('fin-receber-cat').value,
    observacao:document.getElementById('fin-receber-obs').value
  })});
  const d=await r.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  toast('Conta a receber salva!');
  fecharModal('modal-fin-receber');
  finCarregarContasReceber();
}

async function finReceberConta(id){
  if(!confirm('Marcar essa conta como recebida?')) return;
  await fetch(`/api/fin/contas-receber/${id}/receber`,{method:'POST'});
  toast('Conta marcada como recebida');
  finCarregarContasReceber();
}

async function finDeletarContaReceber(id){
  if(!confirm('Excluir essa conta?')) return;
  await fetch(`/api/fin/contas-receber/${id}`,{method:'DELETE'});
  toast('Conta excluída');
  finCarregarContasReceber();
}
