// Descobre e executa todos os testes da interface em Linux e Windows.
const fs=require('node:fs');
const path=require('node:path');
const {spawnSync}=require('node:child_process');

const files=fs.readdirSync(__dirname)
  .filter(name=>name.endsWith('.cjs')&&name!==path.basename(__filename))
  .sort().map(name=>path.join(__dirname,name));
if(!files.length) throw new Error('Nenhum teste de interface encontrado.');
const result=spawnSync(process.execPath,['--test',...files],{stdio:'inherit'});
if(result.error) throw result.error;
process.exit(result.status??1);
