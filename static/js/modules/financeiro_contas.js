// ── Contas a Pagar ────────────────────────────────────────────────────────────
let finFiltroStatusPagar='todos';
let finPagarEstado=criarEstadoLote('contas-pagar');

// Uma leitura compartilhada alimenta tabela, totais e filtros. `valido` também
// representa listas vazias; uma mutação invalida a versão antes de recarregar.
const finLeiturasContas={};
const finCiclosContas={pagar:0,receber:0};
const finValidadeContas=30000;

function finEstadoLeitura(chave){
  return finLeiturasContas[chave]||(finLeiturasContas[chave]={
    valido:false,dados:[],promessa:null,controlador:null,versao:0,carregadoEm:0
  });
}

function finExpirarContas(tipo){
  const estado=finEstadoLeitura(tipo);
  if(estado.valido&&Date.now()-estado.carregadoEm>=finValidadeContas)
    finInvalidarLeituras(tipo==='pagar'?['pagar','alertasPagar']:['receber']);
}

function finInvalidarLeituras(chaves){
  chaves.forEach(chave=>{
    const estado=finEstadoLeitura(chave);
    estado.versao++;
    estado.valido=false;
    if(estado.controlador) estado.controlador.abort();
    estado.controlador=null;
    estado.promessa=null;
  });
}

function finObterLista(chave,url){
  const estado=finEstadoLeitura(chave);
  if(estado.valido) return Promise.resolve(estado.dados);
  if(estado.promessa) return estado.promessa;
  const versao=estado.versao;
  const controlador=new AbortController();
  estado.controlador=controlador;
  const promessa=(async()=>{
    const resposta=await fetch(url,{signal:controlador.signal});
    const dados=await resposta.json();
    if(!resposta.ok||!Array.isArray(dados)) throw new Error(dados?.erro||'Não foi possível carregar os dados.');
    if(versao!==estado.versao){
      const erro=new Error('Leitura substituída');
      erro.name='AbortError';
      throw erro;
    }
    estado.dados=dados;
    estado.valido=true;
    estado.carregadoEm=Date.now();
    return dados;
  })();
  estado.promessa=promessa;
  promessa.finally(()=>{
    if(estado.promessa===promessa){estado.promessa=null;estado.controlador=null;}
  }).catch(()=>{});
  return promessa;
}

function finAvisarLeitura(tipo,mensagem='',falhou=false){
  const pagina=document.getElementById(`page-fin-contas-${tipo}`);
  let aviso=document.getElementById(`fin-aviso-contas-${tipo}`);
  if(!aviso){
    aviso=document.createElement('div');
    aviso.id=`fin-aviso-contas-${tipo}`;
    aviso.style.cssText='margin-bottom:12px;font-size:13px;color:var(--muted)';
    aviso.setAttribute('aria-live','polite');
    pagina.prepend(aviso);
  }
  aviso.hidden=!mensagem;
  aviso.setAttribute('role',falhou?'alert':'status');
  aviso.textContent=mensagem;
  if(falhou){
    const tentar=document.createElement('button');
    tentar.type='button';
    tentar.className='btn btn-ghost btn-sm';
    tentar.style.marginLeft='8px';
    tentar.textContent='Tentar novamente';
    tentar.onclick=()=>tipo==='pagar'
      ?finCarregarContasPagar({atualizar:true}):finCarregarContasReceber({atualizar:true});
    aviso.append(tentar);
  }
}

function finOcuparContas(tipo,ocupado){
  document.getElementById(`page-fin-contas-${tipo}`).setAttribute('aria-busy',String(ocupado));
}

async function finMutarContas(url,opcoes){
  try{
    const resposta=await fetch(url,opcoes);
    const dados=await resposta.json();
    if(!resposta.ok||dados?.ok!==true) throw new Error(dados?.erro||'Não foi possível concluir a alteração.');
    return dados;
  }catch(erro){
    toast(erro.message||'Falha de conexão. Tente novamente.','var(--danger)');
    return null;
  }
}

async function finPrepararCadastrosPagar(){
  try{
    [finCatsPagar,finFornecedores]=await Promise.all([
      finObterLista('categoriasPagar','/api/fin/categorias-pagar'),
      finObterLista('fornecedores','/api/fornecedores')
    ]);
    return true;
  }catch(erro){
    if(erro.name!=='AbortError') toast('Não foi possível carregar categorias e fornecedores. Tente novamente.','var(--danger)');
    return false;
  }
}

function finPreencherFiltrosPagar(){
  const selCat=document.getElementById('fin-filtro-cat-pagar');
  const catValorAtual=selCat.value;
  selCat.innerHTML='<option value="">Todas</option>';
  finCatsPagar.forEach(c=>selCat.add(new Option(c.nome,c.nome)));
  selCat.value=finCatsPagar.some(c=>c.nome===catValorAtual)?catValorAtual:'';
  const selForn=document.getElementById('fin-filtro-forn-pagar');
  const fornValorAtual=selForn.value;
  selForn.innerHTML='<option value="">Todos</option>';
  finFornecedores.forEach(f=>selForn.add(new Option(f.nome,f.id)));
  selForn.value=finFornecedores.some(f=>String(f.id)===fornValorAtual)?fornValorAtual:'';
}

function finAplicarFiltrosPagar(todas){
  const catFiltro=document.getElementById('fin-filtro-cat-pagar').value;
  const mesFiltro=document.getElementById('fin-filtro-mes-pagar').value;
  const fornFiltro=document.getElementById('fin-filtro-forn-pagar').value;
  const hoje=hojeLocal();
  finContasPagar=todas.filter(c=>{
    if(catFiltro&&c.categoria!==catFiltro) return false;
    if(fornFiltro&&String(c.fornecedor_id)!==fornFiltro) return false;
    if(mesFiltro&&!c.vencimento.startsWith(mesFiltro)&&!(c.pago_em||'').startsWith(mesFiltro)) return false;
    if(finFiltroStatusPagar==='vencido') return c.status==='aberto'&&c.vencimento<hoje;
    return finFiltroStatusPagar==='todos'||c.status===finFiltroStatusPagar;
  });
  finRenderContasPagar();
  finAtualizarCardsPagar(todas);
  finCarregarResumoCategorias(todas);
}

async function finCarregarContasPagar({atualizar=false}={}){
  const chaves=['pagar','categoriasPagar','fornecedores','alertasPagar'];
  if(atualizar) finInvalidarLeituras(chaves);
  else finExpirarContas('pagar');
  const ciclo=++finCiclosContas.pagar;
  const carregando=chaves.some(chave=>!finEstadoLeitura(chave).valido);
  finOcuparContas('pagar',carregando);
  if(carregando) finAvisarLeitura('pagar','Atualizando contas…');
  try{
    const [todas,categorias,fornecedores,alertas]=await Promise.all([
      finObterLista('pagar','/api/fin/contas-pagar'),
      finObterLista('categoriasPagar','/api/fin/categorias-pagar'),
      finObterLista('fornecedores','/api/fornecedores'),
      finObterLista('alertasPagar','/api/fin/alertas-vencimento')
    ]);
    if(ciclo!==finCiclosContas.pagar) return false;
    finCatsPagar=categorias;
    finFornecedores=fornecedores;
    finPreencherFiltrosPagar();
    finAplicarFiltrosPagar(todas);
    await finCarregarAlertasVencimento({dados:alertas});
    if(ciclo!==finCiclosContas.pagar) return false;
    finAvisarLeitura('pagar');
    return true;
  }catch(erro){
    if(ciclo===finCiclosContas.pagar&&erro.name!=='AbortError')
      finAvisarLeitura('pagar','Não foi possível atualizar as contas. Os dados exibidos foram mantidos.',true);
    return false;
  }finally{
    if(ciclo===finCiclosContas.pagar) finOcuparContas('pagar',false);
  }
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

function finCarregarResumoCategorias(todas=finEstadoLeitura('pagar').dados){
  const wrap=document.getElementById('fin-resumo-cats-wrap');
  const cont=document.getElementById('fin-resumo-cats');
  const mesFiltro=document.getElementById('fin-filtro-mes-pagar').value;
  if(!mesFiltro){wrap.classList.add('hidden');return;}

  // O resumo mantém os filtros históricos: mês/status, sem categoria/fornecedor.
  // Em "vencidas", o resumo considera todos os status do mês, como a API fazia.
  const grupos=new Map();
  todas.forEach(c=>{
    if(!c.vencimento.startsWith(mesFiltro)&&!(c.pago_em||'').startsWith(mesFiltro)) return;
    if(!['todos','vencido'].includes(finFiltroStatusPagar)&&c.status!==finFiltroStatusPagar) return;
    const grupo=grupos.get(c.categoria)||{categoria:c.categoria,total_valor:0,total_contas:0};
    grupo.total_valor+=c.valor;
    grupo.total_contas++;
    grupos.set(c.categoria,grupo);
  });
  const cats=[...grupos.values()].sort((a,b)=>b.total_valor-a.total_valor||(a.categoria<b.categoria?-1:a.categoria>b.categoria?1:0));
  if(!cats.length){wrap.classList.add('hidden');return;}

  wrap.classList.remove('hidden');
  cont.innerHTML=cats.map(c=>`
    <div class="table-wrap" style="padding:10px 14px;min-width:160px">
      <div style="font-size:11px;color:var(--muted);margin-bottom:2px">${c.categoria}</div>
      <div style="font-weight:700;font-size:16px">${finFmt(c.total_valor)}</div>
      <div style="font-size:11px;color:var(--muted)">${c.total_contas} conta(s)</div>
    </div>`).join('');
}

function finAtualizarCardsPagar(todas=finEstadoLeitura('pagar').dados){
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
  if(!await finPrepararCadastrosPagar()) return;
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
  const d=await finMutarContas(`/api/fin/contas-pagar/${id}`,{method:'PUT',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({
      descricao:desc, valor, vencimento:venc,
      categoria:document.getElementById('fin-editar-cat').value,
      fornecedor_id:document.getElementById('fin-editar-forn').value||null,
      observacao:document.getElementById('fin-editar-obs').value
    })});
  if(!d) return;
  toast('Conta atualizada!');
  fecharModal('modal-fin-editar-pagar');
  await finCarregarContasPagar({atualizar:true});
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
  const d=await finMutarContas(`/api/fin/categorias-pagar/${id}`,{method:'PUT',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({nome})});
  if(!d) return;
  toast('Categoria renomeada!');
  if(await finCarregarContasPagar({atualizar:true})){
    const painel=document.getElementById('fin-cats-painel');
    if(painel.classList.contains('hidden')) finToggleGerenciarCats();
    else finRenderCategorias();
  }
}

async function finCriarCategoria(){
  const nome=document.getElementById('fin-nova-cat-input').value.trim();
  if(!nome){toast('Digite um nome para a categoria','var(--danger)');return;}
  const d=await finMutarContas('/api/fin/categorias-pagar',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({nome})});
  if(!d) return;
  toast('Categoria criada!');
  document.getElementById('fin-nova-cat-input').value='';
  if(await finCarregarContasPagar({atualizar:true})){
    const painel=document.getElementById('fin-cats-painel');
    if(painel.classList.contains('hidden')) finToggleGerenciarCats();
    else finRenderCategorias();
  }
}

async function finExcluirCategoria(id,nome){
  if(!confirm(`Excluir a categoria "${nome}"?\n\nSó é possível excluir categorias sem contas vinculadas.`)) return;
  const d=await finMutarContas(`/api/fin/categorias-pagar/${id}`,{method:'DELETE'});
  if(!d) return;
  toast('Categoria excluída!');
  if(await finCarregarContasPagar({atualizar:true})) finRenderCategorias();
}

async function finAbrirModalPagar(){
  if(finPagarEstado.enviando) return;
  if(reabrirOperacaoPendente(finPagarEstado,'modal-fin-pagar')) return;
  if(!await finPrepararCadastrosPagar()) return;
  finPagarEstado=criarEstadoLote('contas-pagar');
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
  if(finPagarEstado.enviando) return;
  recuperarOperacaoPendente(finPagarEstado);
  const itens=finPagarEstado.incerta?finPagarEstado.payloadOriginal.itens:[];
  if(!finPagarEstado.incerta){
    const desc=document.getElementById('fin-pagar-desc').value.trim();
    const valorTotal=parseFloat(document.getElementById('fin-pagar-valor').value);
    const venc=document.getElementById('fin-pagar-venc').value;
    const n=Number(document.getElementById('fin-pagar-parcelas').value||1);
    if(!desc||!Number.isFinite(valorTotal)||valorTotal<=0){toast('Preencha descrição e valor positivo','var(--danger)');return;}
    if(!Number.isInteger(n)||n<1){toast('Informe uma quantidade válida de parcelas','var(--danger)');return;}

    const cat=document.getElementById('fin-pagar-cat').value;
    const forn=document.getElementById('fin-pagar-forn').value||null;
    const obs=document.getElementById('fin-pagar-obs').value;

    if(n===1){
      if(!venc){toast('Preencha o vencimento','var(--danger)');return;}
      itens.push({descricao:desc,valor:valorTotal,vencimento:venc,
        categoria:cat,fornecedor_id:forn,observacao:obs});
    } else {
      // Validar todas as parcelas antes de enviar a operação única ao servidor.
      for(let i=0;i<n;i++){
        const valorParc=parseFloat(document.getElementById(`fin-parc-val-${i}`)?.value);
        const vencParc=document.getElementById(`fin-parc-venc-${i}`)?.value;
        if(!vencParc||!Number.isFinite(valorParc)||valorParc<=0){
          toast(`Preencha valor e vencimento da parcela ${i+1}/${n}`,'var(--danger)');
          return;
        }
        const descParc=`${desc} ${i+1}/${n}`;
        itens.push({descricao:descParc,valor:valorParc,vencimento:vencParc,
          categoria:cat,fornecedor_id:forn,
          observacao:obs?`${obs} — parcela ${i+1}/${n}`:`Parcela ${i+1}/${n}`});
      }
    }
  }

  const d=await enviarOperacaoAtomica(finPagarEstado,'/api/fin/contas-pagar/lote',{itens},'modal-fin-pagar');
  if(!d) return;
  toast(d.tentativaAnterior?'Conta anterior confirmada. Alterações atuais não foram enviadas.':itens.length===1?'Conta a pagar salva!':`${itens.length} parcelas criadas com sucesso! 💳`);
  fecharModal('modal-fin-pagar');
  try{
    await finCarregarContasPagar({atualizar:true});
  } catch(erro){
    toast('Conta salva. Recarregue a página para atualizar a lista.','var(--danger)');
  }
}

async function finPagarConta(id){
  if(!confirm('Marcar essa conta como paga?')) return;
  if(!await finMutarContas(`/api/fin/contas-pagar/${id}/pagar`,{method:'POST'})) return;
  toast('Conta marcada como paga');
  await finCarregarContasPagar({atualizar:true});
}

async function finDeletarContaPagar(id){
  if(!confirm('Excluir essa conta?')) return;
  if(!await finMutarContas(`/api/fin/contas-pagar/${id}`,{method:'DELETE'})) return;
  toast('Conta excluída');
  await finCarregarContasPagar({atualizar:true});
}

// ── Contas a Receber ──────────────────────────────────────────────────────────
let finFiltroStatusReceber='todos';

async function finCarregarContasReceber({atualizar=false}={}){
  if(atualizar) finInvalidarLeituras(['receber','categoriasReceber']);
  else finExpirarContas('receber');
  const ciclo=++finCiclosContas.receber;
  const carregando=['receber','categoriasReceber'].some(chave=>!finEstadoLeitura(chave).valido);
  finOcuparContas('receber',carregando);
  if(carregando) finAvisarLeitura('receber','Atualizando contas…');
  try{
    const [todas,categorias]=await Promise.all([
      finObterLista('receber','/api/fin/contas-receber'),
      finObterLista('categoriasReceber','/api/fin/categorias-receber')
    ]);
    if(ciclo!==finCiclosContas.receber) return false;
    finCatsReceber=categorias;
    const hoje=hojeLocal();
    finContasReceber=todas.filter(c=>finFiltroStatusReceber==='vencido'
      ?c.vencimento<hoje&&c.status==='aberto'
      :finFiltroStatusReceber==='todos'||c.status===finFiltroStatusReceber);
    finRenderContasReceber();
    finAtualizarCardsReceber(todas);
    finAvisarLeitura('receber');
    return true;
  }catch(erro){
    if(ciclo===finCiclosContas.receber&&erro.name!=='AbortError')
      finAvisarLeitura('receber','Não foi possível atualizar as contas. Os dados exibidos foram mantidos.',true);
    return false;
  }finally{
    if(ciclo===finCiclosContas.receber) finOcuparContas('receber',false);
  }
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

function finAtualizarCardsReceber(todas=finEstadoLeitura('receber').dados){
  const mesFmt=hojeLocal().slice(0,7);
  const aberto=todas.filter(c=>c.status==='aberto').reduce((s,c)=>s+c.valor,0);
  const recebido=todas.filter(c=>c.status==='recebido'&&(c.recebido_em||'').startsWith(mesFmt)).reduce((s,c)=>s+c.valor,0);
  document.getElementById('fin-receber-total-aberto').textContent=finFmt(aberto);
  document.getElementById('fin-receber-total-recebido').textContent=finFmt(recebido);
}

async function finAbrirModalReceber(){
  try{
    finCatsReceber=await finObterLista('categoriasReceber','/api/fin/categorias-receber');
  }catch(erro){
    if(erro.name!=='AbortError') toast('Não foi possível carregar as categorias. Tente novamente.','var(--danger)');
    return;
  }
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
  const d=await finMutarContas('/api/fin/contas-receber',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    descricao:desc, valor, vencimento:venc,
    categoria:document.getElementById('fin-receber-cat').value,
    observacao:document.getElementById('fin-receber-obs').value
  })});
  if(!d) return;
  toast('Conta a receber salva!');
  fecharModal('modal-fin-receber');
  await finCarregarContasReceber({atualizar:true});
}

async function finReceberConta(id){
  if(!confirm('Marcar essa conta como recebida?')) return;
  if(!await finMutarContas(`/api/fin/contas-receber/${id}/receber`,{method:'POST'})) return;
  toast('Conta marcada como recebida');
  await finCarregarContasReceber({atualizar:true});
}

async function finDeletarContaReceber(id){
  if(!confirm('Excluir essa conta?')) return;
  if(!await finMutarContas(`/api/fin/contas-receber/${id}`,{method:'DELETE'})) return;
  toast('Conta excluída');
  await finCarregarContasReceber({atualizar:true});
}
