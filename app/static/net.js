/* NMTPL shared browser transport: timeout, session-expiry handling and user-scoped draft cleanup. */
(function(){
  const DEFAULT_TIMEOUT_MS=20000;
  async function json(url,opts={}){
    const controller=new AbortController();
    const timeoutMs=Number(opts.timeoutMs||DEFAULT_TIMEOUT_MS);
    const timer=setTimeout(()=>controller.abort(),timeoutMs);
    const headers={...(opts.headers||{}),'X-NMTPL-Request':'webapp'};
    const requestOpts={...opts,headers,credentials:'same-origin',signal:opts.signal||controller.signal};
    delete requestOpts.timeoutMs;
    try{
      const response=await fetch(url,requestOpts);
      const raw=await response.text();
      let data=null;
      if(raw){try{data=JSON.parse(raw)}catch(_){data=null}}
      if(!response.ok){
        const message=(data&&typeof data.detail==='string')?data.detail:`Request failed (${response.status})`;
        const error=new Error(message);error.status=response.status;
        if(response.status===401) window.dispatchEvent(new CustomEvent('nmtpl-session-expired'));
        throw error;
      }
      return data;
    }catch(error){
      if(error&&error.name==='AbortError'){
        const e=new Error('Network timeout. Your entry was not confirmed. Check the connection and press Save again.');e.status=0;throw e;
      }
      if(error instanceof TypeError){const e=new Error('Network unavailable. Your draft is still on this device. Reconnect and press Save again.');e.status=0;throw e}
      throw error;
    }finally{clearTimeout(timer)}
  }
  function safeUser(v){return String(v||'anonymous').trim().toLowerCase().replace(/[^a-z0-9_.@+-]/g,'_')}
  function clearUserDrafts(loginId){
    const u=safeUser(loginId);const remove=[];
    for(let i=0;i<localStorage.length;i++){
      const k=localStorage.key(i)||'';
      if((k.startsWith('NMTPL_SIMPLE_DRAFT:')||k.startsWith('NMTPL_SIMPLE_REQ:'))&&k.includes(`:${u}:`))remove.push(k);
      if(k.startsWith(`NMTPL_TIOM_DRAFT:${u}:`))remove.push(k);
    }
    remove.forEach(k=>localStorage.removeItem(k));
  }
  window.NMTPLNet={json,safeUser,clearUserDrafts,DEFAULT_TIMEOUT_MS};
})();
