// ═══════════════════════════════════════
// Relatório de Consumo
// ═══════════════════════════════════════
function abrirRelatorioConsumo(){
  document.getElementById('consumo-resultado').classList.add('hidden');
  document.getElementById('consumo-vazio').classList.remove('hidden');
  // Sugere o mês atual como padrão (não obrigatório, usuário pode trocar)
  const hoje=new Date();
  const primeiroDia=new Date(hoje.getFullYear(), hoje.getMonth(), 1);
  document.getElementById('consumo-inicio').value=dataLocalISO(primeiroDia);
  document.getElementById('consumo-fim').value=dataLocalISO(hoje);
}

async function gerarRelatorioConsumo(){
  const inicio=document.getElementById('consumo-inicio').value;
  const fim=document.getElementById('consumo-fim').value;
  if(!inicio||!fim){toast('Selecione as duas datas','var(--danger)');return;}
  if(inicio>fim){toast('Data início não pode ser depois da data fim','var(--danger)');return;}

  const res=await fetch(`/api/relatorios/consumo?inicio=${inicio}&fim=${fim}`);
  const d=await res.json();
  if(d.erro){toast(d.erro,'var(--danger)');return;}

  document.getElementById('consumo-vazio').classList.add('hidden');
  document.getElementById('consumo-resultado').classList.remove('hidden');

  document.getElementById('consumo-total-produtos').textContent=d.total_produtos;
  document.getElementById('consumo-total-qtd').textContent=d.total_quantidade.toLocaleString('pt-BR');

  if(verLucro()){
    document.getElementById('card-consumo-valor').classList.remove('hidden');
    document.getElementById('consumo-total-valor').textContent=fmtR(d.total_valor);
  }

  // Ranking top 10
  const ranking=document.getElementById('consumo-ranking');
  if(!d.itens.length){
    ranking.innerHTML='<div class="empty">Nenhuma saída registrada neste período.</div>';
  } else {
    const top10=d.itens.slice(0,10);
    const maior=top10[0].total_saida||1;
    ranking.innerHTML=top10.map((item,idx)=>{
      const pct=Math.max((item.total_saida/maior)*100,4);
      return `<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
        <span style="width:22px;font-weight:700;color:var(--muted);font-size:12px">${idx+1}º</span>
        <div style="flex:1">
          <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:3px">
            <span>${item.nome}</span>
            <strong>${item.total_saida.toLocaleString('pt-BR')} ${item.unidade}</strong>
          </div>
          <div style="background:var(--card2);border-radius:4px;height:8px;overflow:hidden">
            <div style="background:var(--accent2);height:100%;width:${pct}%"></div>
          </div>
        </div>
      </div>`;
    }).join('');
  }

  // Tabela detalhada
  const ehAdmin=verLucro();
  document.getElementById('th-consumo-valor').style.display=ehAdmin?'':'none';
  const tbody=document.getElementById('t-consumo');
  if(!d.itens.length){
    tbody.innerHTML=`<tr><td colspan="5" class="empty">Nenhuma saída registrada neste período</td></tr>`;
  } else {
    tbody.innerHTML=d.itens.map(item=>`<tr>
      <td>${item.nome}</td>
      <td>${item.categoria}</td>
      <td>${item.total_saida.toLocaleString('pt-BR')} <span class="badge badge-unit">${item.unidade}</span></td>
      <td>${item.num_movimentacoes}</td>
      ${ehAdmin?`<td>${fmtR(item.valor_consumido)}</td>`:''}
    </tr>`).join('');
  }
}
