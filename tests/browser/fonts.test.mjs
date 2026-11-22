// File/fontconfig fixtures only; actual glyph rendering remains a Chrome check.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mkdtemp,writeFile,readFile,rm,mkdir} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {prepareFonts} from './fonts.mjs';

test('font uses a private disposable configuration without changing system font files',async()=>{
  const root=await mkdtemp(join(tmpdir(),'fire-route-font-test-'));
  try{
    const source=join(root,'fixture.ttf'),profile=join(root,'profile & special');await mkdir(profile);
    await writeFile(source,Buffer.concat([Buffer.from([0,1,0,0]),Buffer.alloc(20)]));
    const before=await readFile(source);const result=await prepareFonts(profile,{source});
    assert.equal(result.mode,'PRIVATE_KOREAN_FONT');
    const xml=await readFile(result.environment.FONTCONFIG_FILE,'utf8');
    assert.ok(xml.includes('profile &amp; special'));assert.ok(xml.includes('/etc/fonts/fonts.conf'));
    assert.deepEqual(await readFile(source),before);
    assert.deepEqual(await readFile(join(profile,'private-fonts/korean-font.ttf')),before);
  }finally{await rm(root,{recursive:true,force:true});}
});
test('invalid explicitly configured font fails without exposing its contents or arbitrary path',async()=>{
  const root=await mkdtemp(join(tmpdir(),'fire-route-font-test-'));
  try{
    const source=join(root,'PRIVATE_FILENAME');await writeFile(source,'PRIVATE_CONTENT_NOT_A_FONT');
    await assert.rejects(prepareFonts(root,{source}),e=>e.message==='Configured Korean font unavailable or invalid');
  }finally{await rm(root,{recursive:true,force:true});}
});
