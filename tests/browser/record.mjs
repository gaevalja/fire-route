// Optional genuine Chrome screencast; recording starts after login is cleared.
import {mkdir,writeFile} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {join} from 'node:path';

export async function record(browser,page,directory) {
  const frames=join(directory,'recording');await mkdir(frames,{recursive:true});
  const rows=[];let pending=Promise.resolve(),failure=false;
  browser.protocol.listeners.set('Page.screencastFrame',event=>{
    if(event.sessionId!==page.sessionId)return;
    const {data,metadata,sessionId}=event.params;
    const index=rows.length;
    if(index>=6000){failure=true;return;}
    rows.push({file:`frame-${String(index).padStart(6,'0')}.jpg`,timestamp:metadata.timestamp});
    pending=pending.then(()=>writeFile(join(frames,rows[index].file),Buffer.from(data,'base64'))).catch(()=>{failure=true;});
    page.request('Page.screencastFrameAck',{sessionId}).catch(()=>{failure=true;});
  });
  await page.request('Page.startScreencast',{format:'jpeg',quality:85,maxWidth:1440,maxHeight:1000,everyNthFrame:1});
  return async()=>{
    await page.request('Page.stopScreencast');
    browser.protocol.listeners.delete('Page.screencastFrame');await pending;
    await writeFile(join(frames,'frames.json'),JSON.stringify({source:'ACTUAL_CHROME_SCREENCAST',rows},null,2));
    if(failure||rows.length<2)return 'CAPTURE_INCOMPLETE';
    let concat='ffconcat version 1.0\n';
    for(let i=0;i<rows.length;i++){
      const duration=i+1<rows.length?rows[i+1].timestamp-rows[i].timestamp:.5;
      if(!Number.isFinite(duration)||duration<0)return 'CAPTURE_TIMESTAMPS_INVALID';
      concat+=`file '${rows[i].file}'\nduration ${Math.max(.001,duration).toFixed(6)}\n`;
    }
    concat+=`file '${rows.at(-1).file}'\n`;await writeFile(join(frames,'capture.ffconcat'),concat);
    const result=await new Promise(resolve=>{
      const child=spawn('ffmpeg',['-nostdin','-y','-loglevel','error','-safe','0','-i','capture.ffconcat',
        '-vf','scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p',
        '-c:v','libx264','-movflags','+faststart','../demo-screen.mp4'],{cwd:frames,stdio:'ignore'});
      child.on('error',()=>resolve('FRAMES_ONLY_FFMPEG_UNAVAILABLE'));
      child.on('exit',code=>resolve(code===0?'RECORDED_SCREEN_ONLY_NO_NARRATION':'ENCODING_FAILED'));
    });
    return result;
  };
}
