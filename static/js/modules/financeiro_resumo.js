// ── Resumo Mensal ─────────────────────────────────────────────────────────────
function finIniciarResumo(){
  const mes=hojeLocal().slice(0,7);
  document.getElementById('fin-resumo-mes').value=mes;
}

async function finCarregarResumo(){
  const mes=document.getElementById('fin-resumo-mes').value;
  if(!mes){toast('Selecione um mês','var(--danger)');return;}
  const d=await fetch(`/api/fin/resumo-mes?mes=${mes}`).then(r=>r.json());
  const conteudo=document.getElementById('fin-resumo-conteudo');
  const vazio=document.getElementById('fin-resumo-vazio');
  if(!d.dias){conteudo.classList.add('hidden');vazio.textContent='Nenhum fechamento registrado para este mês.';vazio.classList.remove('hidden');return;}
  vazio.classList.add('hidden');conteudo.classList.remove('hidden');
  finCarregarMetaResumo(mes);
  const t=d.totais;
  document.getElementById('fin-res-total').textContent=finFmt(t.venda_total);
  document.getElementById('fin-res-dias').textContent=`${d.dias} dia${d.dias>1?'s':''} fechados`;
  document.getElementById('fin-res-cartao').textContent=finFmt(t.cartao_total);
  document.getElementById('fin-res-pix').textContent=finFmt(t.pix);
  document.getElementById('fin-res-dinheiro').textContent=finFmt(t.dinheiro);
  document.getElementById('fin-res-delivery-val').textContent=finFmt(t.delivery_val);
  document.getElementById('fin-res-delivery-qtd').textContent=`${t.delivery_qtd} entregas`;
  document.getElementById('fin-res-frete').textContent=finFmt(t.frete||0);
  document.getElementById('fin-res-paes').textContent=(t.paes_qtd||0).toLocaleString('pt-BR');
  document.getElementById('fin-res-custo-paes').textContent=`custo: ${finFmt(t.custo_paes||0)}`;
  document.getElementById('fin-res-janta').textContent=finFmt(t.janta);
  document.getElementById('fin-res-func').textContent=finFmt(t.func_val||0);
  document.getElementById('fin-res-cortesia').textContent=finFmt(t.cortesia||0);
  const tbody=document.getElementById('t-fin-resumo-dias');
  tbody.innerHTML=d.por_dia.map(r=>{
    const data=new Date(r.data+'T12:00:00').toLocaleDateString('pt-BR',{weekday:'short',day:'2-digit',month:'2-digit'});
    return `<tr>
      <td style="white-space:nowrap">${data}</td>
      <td>${finFmt(r.credito)}</td><td>${finFmt(r.debito)}</td>
      <td>${finFmt(r.voucher)}</td><td>${finFmt(r.pix)}</td>
      <td>${finFmt(r.dinheiro)}</td>
      <td>${finFmt(r.delivery_val)}${r.delivery_qtd?` <span style="color:var(--muted);font-size:11px">(${r.delivery_qtd})</span>`:''}</td>
      <td style="font-weight:700;color:var(--accent2)">${finFmt(r.venda_total)}</td>
    </tr>`;
  }).join('');
}
