// ═══════════════════════════════════════
// Produtos
// ═══════════════════════════════════════
let carregamentoProdutos=null, versaoCarregamentoProdutos=0, controladorProdutos=null;
let paginaProdutos=1, tamanhoPaginaProdutos=50, filtroProdutosAnterior='';

async function carregarProdutos({atualizar=false}={}){
  if(carregamentoProdutos&&!atualizar) return carregamentoProdutos;
  const versao=++versaoCarregamentoProdutos;
  if(controladorProdutos) controladorProdutos.abort();
  const controlador=new AbortController();
  controladorProdutos=controlador;
  const estado=document.getElementById('produtos-status');
  const tabela=document.getElementById('t-produtos');
  estado.hidden=false;
  estado.textContent='Atualizando produtos…';
  tabela.setAttribute('aria-busy','true');
  carregamentoProdutos=(async()=>{
    try{
      const valores=await Promise.all(['/api/produtos','/api/categorias'].map(async url=>{
        const resposta=await fetch(url,{signal:controlador.signal});
        if(!resposta.ok) throw new Error('Não foi possível carregar os produtos.');
        const dados=await resposta.json();
        if(!Array.isArray(dados)) throw new Error('Resposta inválida do servidor.');
        return dados;
      }));
      if(versao!==versaoCarregamentoProdutos) return false;
      [produtos,categorias]=valores;
      construirCatTabs();
      renderProdutos();
      estado.hidden=true;
      return true;
    }catch(erro){
      if(versao===versaoCarregamentoProdutos&&erro.name!=='AbortError')
        estado.innerHTML='Não foi possível atualizar os produtos. Os dados exibidos foram mantidos. <button type="button" class="btn btn-ghost btn-sm" onclick="carregarProdutos({atualizar:true})">Tentar novamente</button>';
      return false;
    }finally{
      if(versao===versaoCarregamentoProdutos){
        tabela.setAttribute('aria-busy','false');
        carregamentoProdutos=null;
        controladorProdutos=null;
      }
    }
  })();
  return carregamentoProdutos;
}

// Sub-nav de categorias na sidebar

// Abas de filtro no topo da tabela de produtos
function construirCatTabs(){
  const el=document.getElementById('cat-tabs');
  const contagens=new Map();
  produtos.forEach(p=>contagens.set(p.categoria_id,(contagens.get(p.categoria_id)||0)+1));
  let html=`<button class="cat-tab ${filtroCatId===null?'active':''}" onclick="filtrarPorCat(null,null,'Produtos')">Todos</button>`;
  categorias.forEach(cat=>{
    const cnt=contagens.get(cat.id)||0;
    if(!cnt) return;
    html+=`<button class="cat-tab ${filtroCatId===cat.id?'active':''}"
               onclick="filtrarPorCat(${cat.id},'${cat.nome}')">${CAT_ICONS[cat.nome]||'🏷️'} ${cat.nome} <span style="opacity:.6;font-size:10px">${cnt}</span></button>`;

  });
  el.innerHTML=html;
}

function filtrarPorCat(catId,label){
  filtroCatId=catId;
  document.getElementById('produtos-titulo').innerHTML=
    catId?`Produtos <small>${label}</small>`:'Produtos';
  construirCatTabs();
  irParaPagina('produtos');
}

const verLucro=()=>me.permissoes.includes('fichas');
function fmtR(v){return 'R$ '+Number(v).toFixed(2).replace('.',',');}

function fmtQtd(p){
  const qtd=p.quantidade;
  const un=p.unidade||'un';
  if(p.sub_qtd_por_un&&p.sub_unidade){
    const total=qtd*p.sub_qtd_por_un;
    return `${qtd} <span class="badge badge-unit">${un}</span> <small style="color:var(--muted)">(${total.toLocaleString('pt-BR')} ${p.sub_unidade})</small>`;
  }
  return `${qtd} <span class="badge badge-unit">${un}</span>`;
}

// Converte uma quantidade qualquer (em unidades) para o agrupamento fardo/caixa/etc do produto,
// usando a mesma lógica da listagem PDF do dashboard.
function fmtQtdComoFardo(qtdUnidades, produto){
  const un=produto.unidade||'un';
  const porFardo=produto.unid_por_fardo;
  const grupoLabel=produto.unid_fardo_label||'fd';
  if(porFardo&&porFardo>0){
    const total=Math.round(qtdUnidades);
    const grupos=Math.floor(total/porFardo);
    const resto=total%porFardo;
    return resto===0?`${grupos} ${grupoLabel}`:`${grupos} ${grupoLabel} + ${resto} ${un}`;
  }
  return `${qtdUnidades} ${un}`;
}

function mudarPaginaProdutos(direcao){
  paginaProdutos+=direcao;
  renderProdutos();
}

function alterarTamanhoPaginaProdutos(valor){
  const tamanho=Number(valor);
  if(![25,50,100].includes(tamanho)) return;
  tamanhoPaginaProdutos=tamanho;
  paginaProdutos=1;
  renderProdutos();
}

function renderProdutos(busca=null){
  filtrarProdutosAoDigitar.cancelar();
  busca=String(busca??document.getElementById('busca-produto').value).trim().toLowerCase();
  let lista=produtos;
  const mostrarInativos=document.getElementById('chk-mostrar-inativos')?.checked;
  const filtro=JSON.stringify([busca,filtroCatId,!!mostrarInativos,tamanhoPaginaProdutos]);
  if(filtro!==filtroProdutosAnterior) paginaProdutos=1;
  filtroProdutosAnterior=filtro;
  if(!mostrarInativos) lista=lista.filter(p=>p.ativo!==0);
  if(filtroCatId) lista=lista.filter(p=>p.categoria_id===filtroCatId);
  if(busca) lista=lista.filter(p=>[p.nome,p.codigo,p.codigo_barras].some(valor=>String(valor??'').toLowerCase().includes(busca)));

  const total=lista.length, paginas=Math.max(1,Math.ceil(total/tamanhoPaginaProdutos));
  paginaProdutos=Math.min(paginas,Math.max(1,paginaProdutos));
  const inicio=(paginaProdutos-1)*tamanhoPaginaProdutos;
  document.getElementById('produtos-total').textContent=total
    ?`${inicio+1}–${Math.min(inicio+tamanhoPaginaProdutos,total)} de ${total} produtos · página ${paginaProdutos} de ${paginas}`
    :'Nenhum produto encontrado';
  document.getElementById('produtos-anterior').disabled=paginaProdutos===1;
  document.getElementById('produtos-proxima').disabled=paginaProdutos===paginas;
  lista=lista.slice(inicio,inicio+tamanhoPaginaProdutos);

  const tbody=document.getElementById('t-produtos');
  if(!lista.length){tbody.innerHTML=`<tr><td colspan="8" class="empty">Nenhum produto${busca?' encontrado':' nesta categoria'}</td></tr>`;return;}

  tbody.innerHTML=lista.map(p=>{
    const inativo=p.ativo===0;
    const status=inativo?'<span class="badge" style="background:rgba(148,163,184,.15);color:var(--muted)">Inativo</span>':
      p.quantidade===0?'<span class="badge badge-danger">Sem estoque</span>':
      p.quantidade<=p.estoque_min?'<span class="badge badge-warn">Baixo</span>':'<span class="badge badge-ok">OK</span>';
    const temV=p.preco_venda!=null&&+p.preco_venda>0;
    let lucroHtml='<span class="lucro-dash">—</span>';
    if(temV){const lc=+p.preco_venda-+p.preco_custo;const pct=+p.preco_custo>0?(lc/+p.preco_custo)*100:null;
      lucroHtml=`<span class="${lc>=0?'lucro-pos':'lucro-neg'}">${fmtR(lc)}${pct!==null?` <small>(${pct>=0?'+':''}${pct.toFixed(1)}%)</small>`:''}</span>`;}
    return `<tr style="${inativo?'opacity:.5':''}">
      <td>${p.nome}</td><td><code>${p.codigo}</code></td>
      <td>${fmtQtd(p)}</td>
      <td>${fmtR(+p.preco_custo)}</td>
      ${verLucro()?`<td>${temV?fmtR(+p.preco_venda):'—'}</td><td>${lucroHtml}</td>`:''}
      <td>${status}</td>
      <td>${me.permissoes.includes('produtos')?`
        <button class="btn btn-ghost btn-sm" onclick="editarProduto(${p.id})" title="Editar">✏️</button>
        <button class="btn ${inativo?'btn-success':'btn-ghost'} btn-sm" onclick="alternarAtivoProduto(${p.id},${inativo})" title="${inativo?'Reativar produto':'Desativar produto (mantém histórico)'}">${inativo?'▶️':'⏸️'}</button>
        <button class="btn btn-danger btn-sm" onclick="deletarProduto(${p.id},'${p.nome.replace(/'/g,"\\'")}')" title="Excluir permanentemente">🗑️</button>`:'—'}
      </td></tr>`;
  }).join('');
}
const filtrarProdutosAoDigitar=adiarBusca(()=>renderProdutos());
document.getElementById('busca-produto').addEventListener('input',filtrarProdutosAoDigitar);

async function alternarAtivoProduto(id, ativarAgora){
  const p=produtos.find(x=>x.id===id); if(!p) return;
  if(!ativarAgora && !confirm(`Desativar "${p.nome}"?\n\nO produto some das telas de uso diário (dashboard, listas, inventário), mas o histórico é mantido e você pode reativar quando quiser.`)) return;
  const res=await fetch(`/api/produtos/${id}/ativo`,{method:'PUT',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({ativo:ativarAgora})});
  const d=await res.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}
  p.ativo=d.ativo?1:0;
  toast(d.ativo?`"${p.nome}" reativado!`:`"${p.nome}" desativado.`);
  renderProdutos(document.getElementById('busca-produto').value.toLowerCase());
}

// Subdivisão preview
function calcularTotalSubdiv(){
  const qtd=+document.getElementById('p-qtd').value||0;
  const sub=+document.getElementById('p-sub-qtd').value||0;
  const sunid=document.getElementById('p-sub-unidade').value;
  const unid=document.getElementById('p-unidade').value;
  const prev=document.getElementById('subdiv-preview');
  if(qtd>0&&sub>0&&sunid){
    const total=qtd*sub;
    prev.textContent=`= ${qtd} ${unid} × ${sub} ${sunid} = ${total.toLocaleString('pt-BR')} ${sunid} no total`;
  } else {prev.textContent='';}
}

function calcularConversaoFardo(){
  const qtd=+document.getElementById('p-qtd').value||0;
  const porFardo=+document.getElementById('p-unid-fardo').value||0;
  const grupoLabel=document.getElementById('p-unid-fardo-label').value||'fd';
  const unid=document.getElementById('p-unidade').value||'un';
  const prev=document.getElementById('conversao-fardo-preview');
  if(qtd>0&&porFardo>0){
    const total=Math.round(qtd);
    const grupos=Math.floor(total/porFardo);
    const resto=total%porFardo;
    const txt=resto===0?`${grupos} ${grupoLabel}`:`${grupos} ${grupoLabel} + ${resto} ${unid}`;
    prev.textContent=`Na impressão aparecerá: ${txt}`;
  } else {prev.textContent='';}
}


function abrirModalProduto(p=null){
  editandoProdId=p?p.id:null;
  document.getElementById('mp-titulo').textContent=p?'Editar Produto':'Novo Produto';
  const selCat=document.getElementById('p-categoria');
  selCat.innerHTML='<option value="">Sem categoria</option>'+
    categorias.map(c=>`<option value="${c.id}">${c.nome}</option>`).join('');
  document.getElementById('p-nome').value=p?.nome||'';
  document.getElementById('p-codigo-barras').value=p?.codigo_barras||'';
  // Sugerir próximo código livre ao criar novo produto
  if(!p){
    const codigos=produtos.map(x=>+x.codigo).filter(n=>!isNaN(n)&&n>0);
    let proximo=1;
    if(codigos.length){
      codigos.sort((a,b)=>a-b);
      for(let i=1;i<=codigos[codigos.length-1]+1;i++){
        if(!codigos.includes(i)){proximo=i;break;}
      }
    }
    document.getElementById('p-codigo').value=String(proximo).padStart(2,'0');
  } else {
    document.getElementById('p-codigo').value=p.codigo;
  }
  document.getElementById('p-unidade').value=p?.unidade||'un';
  document.getElementById('p-min').value=p?.estoque_min??5;
  document.getElementById('p-qtd').value=p?.quantidade??0;
  document.getElementById('p-sub-qtd').value=p?.sub_qtd_por_un||'';
  document.getElementById('p-sub-unidade').value=p?.sub_unidade||'';
  document.getElementById('p-unid-fardo').value=p?.unid_por_fardo||'';
  document.getElementById('p-unid-fardo-label').value=p?.unid_fardo_label||'fd';
  document.getElementById('p-validade').value=p?.validade||'';
  document.getElementById('p-custo').value=p?.preco_custo??0;
  document.getElementById('p-venda').value=(p?.preco_venda!=null&&p?.preco_venda!=='')?p.preco_venda:'';
  // Campos de embalagem
  document.getElementById('p-preco-embalagem').value=p?.preco_embalagem||'';
  document.getElementById('p-tipo-embalagem').value=p?.tipo_embalagem||'';
  document.getElementById('p-unid-embalagem').value=p?.unid_embalagem||'';
  prodAtualizarCustoUnitario();
  document.getElementById('subdiv-preview').textContent='';
  document.getElementById('conversao-fardo-preview').textContent='';
  if(p?.categoria_id) selCat.value=p.categoria_id;
  // esconde qtd na edição
  document.getElementById('wrap-qtd-principal').style.display=p?'none':'';
  document.getElementById('modal-produto').classList.remove('hidden');
  if(p) calcularConversaoFardo();
  fornecedoresPendentes=[];
  carregarFornecedoresDoProduto(p?.id||null);
}
function prodAtualizarCustoUnitario(){
  const precoEmb=parseFloat(document.getElementById('p-preco-embalagem').value)||0;
  const tipoEmb=document.getElementById('p-tipo-embalagem').value;
  const unidEmb=parseInt(document.getElementById('p-unid-embalagem').value)||0;
  const wrap=document.getElementById('p-custo-calculado-wrap');
  const origemEl=document.getElementById('p-custo-origem');

  if(precoEmb>0 && unidEmb>0 && tipoEmb){
    const custoUnit=precoEmb/unidEmb;
    document.getElementById('p-custo-calculado').value=
      'R$ '+custoUnit.toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:4});
    document.getElementById('p-custo-calc-desc').textContent=
      `R$ ${precoEmb.toLocaleString('pt-BR',{minimumFractionDigits:2})} ÷ ${unidEmb} un = R$ ${custoUnit.toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:4})} por unidade`;
    wrap.classList.remove('hidden');
    // Preenche o preço de custo automaticamente
    document.getElementById('p-custo').value=custoUnit.toFixed(4);
    origemEl.textContent=`Calculado: ${tipoEmb} de ${unidEmb} un × R$ ${(1/unidEmb*precoEmb).toLocaleString('pt-BR',{minimumFractionDigits:2})}`;
  } else {
    wrap.classList.add('hidden');
    origemEl.textContent='';
  }
}

function editarProduto(id){const p=produtos.find(x=>x.id===id);if(p)abrirModalProduto(p);}

async function salvarProduto(){
  const pv=document.getElementById('p-venda').value;
  const sq=document.getElementById('p-sub-qtd').value;
  const body={
    nome:document.getElementById('p-nome').value.trim(),
    codigo:document.getElementById('p-codigo').value.trim(),
    unidade:document.getElementById('p-unidade').value,
    categoria_id:document.getElementById('p-categoria').value||null,
    estoque_min:+document.getElementById('p-min').value,
    quantidade:+document.getElementById('p-qtd').value,
    sub_qtd_por_un:sq===''?null:+sq,
    sub_unidade:document.getElementById('p-sub-unidade').value||null,
    unid_por_fardo:document.getElementById('p-unid-fardo').value===''?null:+document.getElementById('p-unid-fardo').value,
    unid_fardo_label:document.getElementById('p-unid-fardo-label').value||'fd',
    validade:document.getElementById('p-validade').value||null,
    preco_custo:+document.getElementById('p-custo').value,
    preco_venda:pv===''?null:+pv,
    preco_embalagem:document.getElementById('p-preco-embalagem').value===''?null:+document.getElementById('p-preco-embalagem').value,
    tipo_embalagem:document.getElementById('p-tipo-embalagem').value||null,
    unid_embalagem:document.getElementById('p-unid-embalagem').value===''?null:+document.getElementById('p-unid-embalagem').value,
    codigo_barras:document.getElementById('p-codigo-barras').value.trim()||null,
  };
  if(!body.nome||!body.codigo){toast('Preencha nome e código','var(--danger)');return;}
  const res=await fetch(editandoProdId?`/api/produtos/${editandoProdId}`:'/api/produtos',
    {method:editandoProdId?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await res.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}

  // Se for produto novo e tiver fornecedores pendentes, vincula agora que já temos o ID
  if(!editandoProdId && fornecedoresPendentes.length){
    const novoId=d.id;
    for(const v of fornecedoresPendentes){
      await fetch(`/api/produtos/${novoId}/fornecedores`,{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({fornecedor_id:v.fornecedor_id, preco:v.preco})});
    }
    fornecedoresPendentes=[];
  }

  toast(editandoProdId?'Produto atualizado!':'Produto criado!');
  fecharModal('modal-produto'); await carregarProdutos({atualizar:true});
}
async function deletarProduto(id,nome){
  if(!confirm(`Excluir "${nome}"?`))return;
  await fetch(`/api/produtos/${id}`,{method:'DELETE'});
  toast('Removido','var(--danger)'); await carregarProdutos({atualizar:true});
}

// ═══════════════════════════════════════
// Subcategorias
// ═══════════════════════════════════════
