/* Headless wrapper; imported config/engine remain byte-for-byte unchanged. */
'use strict';
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const {parseArgs}=require('node:util');
const {values}=parseArgs({options:{seed:{type:'string',default:'2026'},wind:{type:'string',default:'5'},seconds:{type:'string',default:'600'},output:{type:'string',default:'.runtime/fire-evac-trace.jsonl'}}});
function integer(raw,min,max){const n=Number(raw);if(!/^\d+$/.test(raw)||!Number.isSafeInteger(n)||n<min||n>max)throw new Error('Invalid scenario numeric argument');return n;}
const seed=integer(values.seed,1,2147483647),wind=integer(values.wind,1,15),seconds=integer(values.seconds,0,12000);
if(![1,5,10,15].includes(wind))throw new Error('Unsupported wind');
const source=path.join(__dirname,'scenarios/fire_evac');
const manifest=JSON.parse(fs.readFileSync(path.join(source,'manifest.json'),'utf8'));
const hashes={};
for(const name of Object.keys(manifest.files_sha256).sort()){
  if(!['README.md','config.js','engine.js','app.js','index.html','styles.css','test_engine.js'].includes(name))throw new Error('Unexpected source file');
  hashes[name]=crypto.createHash('sha256').update(fs.readFileSync(path.join(source,name))).digest('hex');
  if(hashes[name]!==manifest.files_sha256[name])throw new Error('Imported source changed');
}
if(Object.keys(hashes).length!==7||crypto.createHash('sha256').update(JSON.stringify(hashes)).digest('hex')!==manifest.bundle_sha256)throw new Error('Source manifest differs');
require(path.join(source,'config.js'));require(path.join(source,'engine.js'));
const engine=globalThis.FireEvacEngine;
const output=path.resolve(values.output);fs.mkdirSync(path.dirname(output),{recursive:true,mode:0o700});
const temporary=output+'.'+crypto.randomUUID()+'.tmp';let fd;
const traceHash=crypto.createHash('sha256');
let count=0,state=engine.createSimulation({seed,wind});
try{
  fd=fs.openSync(temporary,'wx',0o600);
  while(true){
    const frame={schema_version:1,profile_id:manifest.profile_id,source_manifest_sha256:manifest.bundle_sha256,seed:state.seed,wind_mps:state.wind,simulation_second:state.second,ended:state.ended,
      zones:Object.values(state.zones).map(z=>({zone_id:z.id,fire_index:z.fire,smoke_index:z.smoke,collapsed:z.collapsed}))};
    const line=JSON.stringify(frame)+'\n';fs.writeSync(fd,line);traceHash.update(line);count++;
    if(state.ended||state.second>=seconds)break;
    state=engine.stepSimulation(state);
  }
  fs.fsyncSync(fd);fs.closeSync(fd);fd=undefined;fs.renameSync(temporary,output);
}catch(error){if(fd!==undefined)fs.closeSync(fd);if(fs.existsSync(temporary))fs.unlinkSync(temporary);throw error;}
console.log(JSON.stringify({state:'EXPORTED',kind:'SYNTHETIC_SOURCE_REPLAY_NOT_CSE',node:process.version,seed,wind_mps:wind,source_manifest_sha256:manifest.bundle_sha256,trace_sha256:traceHash.digest('hex'),frames:count,last_simulation_second:state.second,ended:state.ended,path:values.output}));
