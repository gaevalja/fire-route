// Personal machine fonts are copied only into the disposable Chrome profile.
// No Windows font, license-restricted binary, or system font setting is published.
import {readFile,writeFile,copyFile,mkdir,stat} from 'node:fs/promises';
import {join,resolve} from 'node:path';

const escapeXML=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');

export async function prepareFonts(profile,{source=process.env.FIREROUTE_KOREAN_FONT}={}) {
  const explicit=!!source;
  const candidates=source?[resolve(source)]:[
    '/mnt/c/Windows/Fonts/NotoSansKR-VF.ttf',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
  ];
  for(const candidate of candidates){
    try{
      const info=await stat(candidate);
      if(!info.isFile()||info.size<12||info.size>64*1024*1024)throw new Error('Invalid font');
      const data=await readFile(candidate);
      const magic=data.subarray(0,4);
      if(!magic.equals(Buffer.from([0,1,0,0]))&&!['OTTO','ttcf'].includes(magic.toString('ascii')))
        throw new Error('Invalid font');
      const directory=join(profile,'private-fonts');await mkdir(directory);
      await copyFile(candidate,join(directory,'korean-font.ttf'));
      const configuration=join(profile,'fonts.conf');
      await writeFile(configuration,`<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd"><fontconfig><include ignore_missing="yes">/etc/fonts/fonts.conf</include><dir>${escapeXML(directory)}</dir><cachedir>${escapeXML(join(profile,'font-cache'))}</cachedir></fontconfig>`,{mode:0o600});
      return {environment:{FONTCONFIG_FILE:configuration},mode:'PRIVATE_KOREAN_FONT'};
    }catch{
      if(explicit)throw new Error('Configured Korean font unavailable or invalid');
    }
  }
  return {environment:{},mode:'SYSTEM_FONTS_ONLY_REQUIRES_VISUAL_REVIEW'};
}
