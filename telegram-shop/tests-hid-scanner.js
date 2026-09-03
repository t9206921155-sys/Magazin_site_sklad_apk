// Проверка логики HID-парсера, извлечённой из warehouse/app.js
const FAST_MS=35, IDLE_FLUSH=120, MIN_LEN=4, DEDUP_MS=700;

function makeParser(hasSuffix=true){
  let buf='', lastKeyTime=0, lastCode='', lastAt=0, timer=null;
  const out=[];
  const submit=(code,now)=>{ if(timer){clearTimeout(timer);timer=null;} buf='';
    if(!code||code.length<MIN_LEN) return;
    if(code===lastCode && now-lastAt<DEDUP_MS) return;
    lastCode=code; lastAt=now; out.push(code); };
  return {
    key(k,now){
      const delta=now-lastKeyTime; lastKeyTime=now;
      if(k==='Enter'){ const c=buf.trim(); if(c) submit(c,now); return; }
      if(k.length!==1) return;
      if(delta>FAST_MS) buf='';
      buf+=k;
      if(timer) clearTimeout(timer);
      timer=setTimeout(()=>{ const c=buf.trim();
        if(!hasSuffix && c.length>=MIN_LEN) submit(c,Date.now()); else buf=''; },IDLE_FLUSH);
    },
    idle(now){ const c=buf.trim(); if(timer){clearTimeout(timer);timer=null;}
      if(!hasSuffix && c.length>=MIN_LEN) submit(c,now); else buf=''; },
    out, get buf(){return buf;}
  };
}
const scan=(p,code,t0,step=10)=>{let t=t0;for(const ch of code){p.key(ch,t);t+=step;}return t;};
let pass=0,fail=0;
const ok=(n,c)=>{c?(pass++,console.log('  ✅ '+n)):(fail++,console.log('  ❌ '+n));};

console.log('1) Сканер с Enter-суффиксом');
{const p=makeParser(true);let t=scan(p,'4600000000001',1000);p.key('Enter',t);
 ok('код принят целиком',p.out.length===1&&p.out[0]==='4600000000001');}

console.log('2) Два скана подряд НЕ склеиваются (был баг)');
{const p=makeParser(true);let t=scan(p,'1111111111111',1000);p.key('Enter',t);
 t=scan(p,'2222222222222',t+500);p.key('Enter',t);
 ok('два разных кода',p.out.length===2&&p.out[0]==='1111111111111'&&p.out[1]==='2222222222222');}

console.log('3) Скан без Enter не оставляет мусор в буфере (был баг)');
{const p=makeParser(true);let t=scan(p,'9999999999999',1000);p.idle(t+200);
 t=scan(p,'8888888888888',t+400);p.key('Enter',t);
 ok('второй код чистый',p.out.length===1&&p.out[0]==='8888888888888');}

console.log('4) Медленный ручной ввод не считается сканом (был баг)');
{const p=makeParser(true);let t=1000;for(const ch of 'abcd'){p.key(ch,t);t+=300;}
 ok('буфер не накопил всё',p.buf.length<=1);}

console.log('5) Дедупликация повторного скана');
{const p=makeParser(true);let t=scan(p,'5555555555555',1000);p.key('Enter',t);
 t=scan(p,'5555555555555',t+100);p.key('Enter',t);
 ok('второй раз отброшен',p.out.length===1);
 let t2=scan(p,'5555555555555',t+2000);p.key('Enter',t2);
 ok('после паузы принят снова',p.out.length===2);}

console.log('6) Сканер без Enter — отправка по паузе');
{const p=makeParser(false);let t=scan(p,'7777777777777',1000);p.idle(t+200);
 ok('код отправлен по паузе',p.out.length===1&&p.out[0]==='7777777777777');}

console.log('7) Слишком короткий код игнорируется');
{const p=makeParser(true);let t=scan(p,'12',1000);p.key('Enter',t);
 ok('шум отброшен',p.out.length===0);}

console.log(`\nИтог: ${pass} passed, ${fail} failed`);
process.exit(fail?1:0);
