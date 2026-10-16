// Agrupa a digitação sem atrasar ações explícitas, como leitura de código de barras.
function adiarBusca(funcao, espera=150){
  let temporizador=null, argumentos=null, contexto=null;
  function cancelar(){
    if(temporizador!==null) clearTimeout(temporizador);
    temporizador=null;
    argumentos=null;
    contexto=null;
  }
  function executar(){
    if(argumentos===null) return;
    const valores=argumentos, origem=contexto;
    cancelar();
    return funcao.apply(origem,valores);
  }
  function adiada(...valores){
    cancelar();
    argumentos=valores;
    contexto=this;
    temporizador=setTimeout(executar,espera);
  }
  adiada.cancelar=cancelar;
  adiada.executar=executar;
  return adiada;
}

// Cada palavra pode aparecer em qualquer posição; acentos e caixa não interferem.
function normalizarTextoBusca(valor){
  return String(valor??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
}

function termosDaBusca(busca){
  return normalizarTextoBusca(busca).trim().split(/\s+/).filter(Boolean);
}

function textoCorrespondeBusca(texto,busca){
  const termos=Array.isArray(busca)?busca:termosDaBusca(busca);
  const normalizado=normalizarTextoBusca(texto);
  return termos.every(termo=>normalizado.includes(termo));
}

function produtoCorrespondeBusca(produto,busca){
  return textoCorrespondeBusca([produto.nome,produto.codigo,produto.codigo_barras]
    .map(valor=>valor??'').join(' '),busca);
}
