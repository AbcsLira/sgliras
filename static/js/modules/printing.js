// ═══════════════════════════════════════
// Listagem PDF
// ═══════════════════════════════════════
function gerarListagemPDF(){
  // Preencher chips de categorias
  const chips=document.getElementById('lst-cat-chips');
  const cats=[...new Set(produtos.map(p=>p.categoria).filter(Boolean))].sort();
  chips.innerHTML=cats.map(c=>`<span class="filter-chip cat-chip" data-cat="${c}" onclick="toggleCatChip(this)">${c}</span>`).join('');
  document.getElementById('lst-nome').value='';
  document.getElementById('lst-preview').textContent='';
  document.getElementById('lst-mostrar-precos').checked=false;
  // Resetar filtro de estoque para "Todos"
  document.querySelectorAll('#lst-estoque-chips .filter-chip').forEach((c,i)=>c.classList.toggle('active',i===0));
  document.getElementById('modal-listagem').classList.remove('hidden');
  setTimeout(()=>document.getElementById('lst-nome').focus(),80);
}

function toggleCatChip(el){
  el.classList.toggle('active');
  atualizarPreviewListagem();
}

function lstSetEstoqueFiltro(el){
  document.querySelectorAll('#lst-estoque-chips .filter-chip').forEach(c=>c.classList.remove('active'));
  el.classList.add('active');
  atualizarPreviewListagem();
}

function lstGetEstoqueFiltro(){
  return document.querySelector('#lst-estoque-chips .filter-chip.active')?.dataset.modo||'todos';
}

function lstFiltrarPorEstoque(lista, modo){
  if(modo==='baixo')        return lista.filter(p=>p.quantidade>0 && p.quantidade<=p.estoque_min);
  if(modo==='zerado')       return lista.filter(p=>p.quantidade<=0);
  if(modo==='baixo-zerado') return lista.filter(p=>p.quantidade<=p.estoque_min);
  return lista;
}

document.addEventListener('DOMContentLoaded',()=>{
  document.getElementById('lst-nome')?.addEventListener('input', atualizarPreviewListagem);
});

function atualizarPreviewListagem(){
  const nome=document.getElementById('lst-nome').value.trim().toLowerCase();
  const cats=[...document.querySelectorAll('#lst-cat-chips .cat-chip.active')].map(e=>e.dataset.cat);
  let lista=produtos;
  if(cats.length) lista=lista.filter(p=>cats.includes(p.categoria));
  if(nome) lista=lista.filter(p=>p.nome.toLowerCase().includes(nome));
  lista=lstFiltrarPorEstoque(lista, lstGetEstoqueFiltro());
  const prev=document.getElementById('lst-preview');
  if(lista.length===0) prev.innerHTML='<span style="color:var(--danger)">Nenhum produto encontrado com esses filtros.</span>';
  else prev.innerHTML=`<span style="color:var(--accent2)">✓ ${lista.length} produto${lista.length>1?'s':''} serão listados</span>`;
}

async function confirmarListagem(){
  const nome=document.getElementById('lst-nome').value.trim();
  const cats=[...document.querySelectorAll('#lst-cat-chips .cat-chip.active')].map(e=>e.dataset.cat);
  // Se múltiplas categorias, gera uma requisição por vez passando a primeira
  // Se nenhuma, passa vazio (todas)
  const params=new URLSearchParams();
  if(nome) params.set('nome', nome);
  if(cats.length===1) params.set('categoria', cats[0]);
  // Para múltiplas categorias, filtramos no front após buscar tudo
  const url='/api/listagem-pdf'+(params.toString()?'?'+params.toString():'');
  fecharModal('modal-listagem');
  const d=await fetch(url).then(r=>r.json());

  // Filtro adicional no front para múltiplas categorias
  let grupos=d.grupos;
  if(cats.length>1){
    grupos={};
    for(const [g,itens] of Object.entries(d.grupos)){
      const catBase=g.split(' › ')[0];
      if(cats.includes(catBase)) grupos[g]=itens;
    }
  }

  // Filtro de situação de estoque
  const modoEstoque=lstGetEstoqueFiltro();
  if(modoEstoque!=='todos'){
    const filtrados={};
    for(const [g,itens] of Object.entries(grupos)){
      const sel=lstFiltrarPorEstoque(itens, modoEstoque);
      if(sel.length) filtrados[g]=sel;
    }
    grupos=filtrados;
  }

  const fmtR=v=>'R$ '+Number(v).toFixed(2).replace('.',',');
  const rotulosEstoque={'baixo':'Estoque baixo','zerado':'Zerados','baixo-zerado':'Baixo e zerados'};
  const mostrarPrecos=document.getElementById('lst-mostrar-precos').checked;
  const exibirPrecos=d.eh_admin && mostrarPrecos;
  let tituloFiltro=nome&&cats.length? `"${nome}" em ${cats.join(', ')}`:
                     nome? `"${nome}"`:
                     cats.length? cats.join(', ') : 'Todos os produtos';
  if(modoEstoque!=='todos') tituloFiltro+=` · ${rotulosEstoque[modoEstoque]}`;

  let html=`<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">
  <title>Listagem de Estoque — S.G. Lira's</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:Arial,sans-serif;font-size:12px;color:#111;padding:20px}
    h1{font-size:18px;font-weight:bold;margin-bottom:2px}
    .sub{font-size:11px;color:#666;margin-bottom:16px}
    .grupo{margin-bottom:18px;break-inside:avoid}
    .grupo-titulo{background:#1a1d27;color:#fff;padding:6px 10px;font-weight:bold;
                  font-size:12px;text-transform:uppercase;letter-spacing:.5px;margin-bottom:0}
    table{width:100%;border-collapse:collapse}
    th{background:#f0f0f0;padding:6px 10px;text-align:left;font-size:11px;
       text-transform:uppercase;letter-spacing:.4px;border-bottom:2px solid #ddd}
    td{padding:6px 10px;border-bottom:1px solid #eee;font-size:12px}
    tr:nth-child(even) td{background:#fafafa}
    .qtd{font-weight:bold}
    .status-ok{color:#16a34a}.status-baixo{color:#d97706}.status-zero{color:#dc2626;font-weight:bold}
    .total-row td{font-weight:bold;background:#f5f5f5;border-top:2px solid #ccc}
    .rodape{margin-top:20px;font-size:10px;color:#888;border-top:1px solid #ddd;padding-top:8px;text-align:right}
    .aviso-sem-preco{background:#eef2ff;color:#3730a3;padding:6px 10px;border-radius:6px;font-size:11px;margin-bottom:14px;display:inline-block}
    @media print{body{padding:10px}.rodape{position:fixed;bottom:0;width:100%}}
    /* ── Módulo Financeiro ── */
    .fin-campo-grupo{margin-bottom:12px}
    .fin-label{display:block;font-size:11.5px;color:var(--muted);margin-bottom:5px;font-weight:500}
    .fin-input{width:100%;padding:8px 11px;border-radius:10px;border:1px solid var(--border);
               background:rgba(255,255,255,.04);color:var(--text);font-size:13px;transition:.2s}
    .fin-input:focus{outline:none;border-color:var(--accent);background:rgba(79,124,255,.06)}
    /* Ícone do seletor de data/mês: inverte para ficar visível em fundo escuro */
    input[type="date"]::-webkit-calendar-picker-indicator,
    input[type="month"]::-webkit-calendar-picker-indicator{
      filter:invert(1) brightness(1.4);cursor:pointer;
    }
    .fin-badge-aberto{background:rgba(245,158,11,.15);color:var(--warn);padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600}
    .fin-badge-pago{background:rgba(34,197,94,.15);color:var(--accent2);padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600}
    .fin-badge-recebido{background:rgba(34,197,94,.15);color:var(--accent2);padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600}
    .fin-badge-vencido{background:rgba(239,68,68,.15);color:var(--danger);padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600}
    /* Scroll horizontal elegante em tabelas largas */
    .table-wrap[style*="overflow-x"]{scrollbar-width:thin;scrollbar-color:rgba(255,255,255,.1) transparent}
    .table-wrap[style*="overflow-x"]::-webkit-scrollbar{height:4px}
    .table-wrap[style*="overflow-x"]::-webkit-scrollbar-track{background:transparent}
    .table-wrap[style*="overflow-x"]::-webkit-scrollbar-thumb{background:rgba(255,255,255,.12);border-radius:4px}
  </style></head><body>
  <h1>📦 Listagem de Estoque — S.G. Lira's</h1>
  <div class="sub">Filtro: ${tituloFiltro} · Gerado em ${d.gerado_em}</div>
  ${!exibirPrecos?'<div class="aviso-sem-preco">💡 Lista sem preços — indicada para contagem física</div>':''}`;

  for(const [grupo, itens] of Object.entries(grupos)){
    html+=`<div class="grupo">
      <div class="grupo-titulo">${grupo} <span style="font-weight:normal;opacity:.7">(${itens.length} produto${itens.length>1?'s':''})</span></div>
      <table><thead><tr>
        <th>Produto</th><th>Código</th><th>Quantidade</th><th>Status</th>
        ${exibirPrecos?'<th>Custo unit.</th><th>Valor total</th>':''}
      </tr></thead><tbody>`;

    let totalGrupo=0;
    itens.forEach(p=>{
      const qtd=+p.quantidade;
      const status=qtd===0?'<span class="status-zero">⛔ Sem estoque</span>':
        qtd<=+p.estoque_min?'<span class="status-baixo">⚠️ Baixo</span>':
        '<span class="status-ok">✓ OK</span>';
      if(exibirPrecos) totalGrupo+=p.valor_total_item||0;
      html+=`<tr>
        <td>${p.nome}</td>
        <td style="color:#666;font-size:11px">${p.codigo}</td>
        <td class="qtd">${p.qtd_display}</td>
        <td>${status}</td>
        ${exibirPrecos?`<td>${fmtR(p.preco_custo)}</td><td>${fmtR(p.valor_total_item)}</td>`:''}
      </tr>`;
    });

    if(exibirPrecos){
      html+=`<tr class="total-row"><td colspan="5" style="text-align:right">Subtotal ${grupo}:</td>
             <td>${fmtR(totalGrupo)}</td></tr>`;
    }
    html+=`</tbody></table></div>`;
  }

  if(exibirPrecos&&d.total_geral!==null){
    html+=`<div style="text-align:right;font-size:14px;font-weight:bold;margin-top:8px;padding:10px;
                background:#1a1d27;color:#38e0a0;border-radius:6px">
      💰 VALOR TOTAL EM ESTOQUE: R$ ${d.total_geral.toLocaleString('pt-BR',{minimumFractionDigits:2})}
    </div>`;
  }

  html+=`<div class="rodape">S.G. Lira's · ${d.gerado_em}</div>
  <script>window.onload=()=>setTimeout(()=>window.print(),300);<\/script>
  </body></html>`;

  const blob=new Blob([html],{type:'text/html;charset=utf-8'});
  const blobUrl=URL.createObjectURL(blob);
  const a=document.createElement('a');
  a.href=blobUrl;
  a.target='_blank';
  a.click();
  setTimeout(()=>URL.revokeObjectURL(blobUrl), 60000);
}
