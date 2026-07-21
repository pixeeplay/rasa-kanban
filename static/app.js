const COLS = ["todo", "doing", "done"];
const LABELS = { todo: "À faire", doing: "En cours", done: "Fait" };
let state = { boards: {}, updated: 0 };
let dragging = null;      // {board,col,id}
let busy = false;         // suppress polling during local edits
let who = localStorage.getItem("kanban_who") || "";

function esc(s){return (s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function toast(m){const t=document.getElementById("toast");t.textContent=m;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),1800);}

async function api(path, opts){const r=await fetch(path,opts);return r.json();}

async function pull(force){
  const s = await api("/api/state");
  if (force || (!busy && (s.updated||0) > (state.updated||0))) { state = s; render(); }
}

async function push(){
  document.getElementById("save").textContent = "…";
  state.updated = Date.now()/1000;
  await api("/api/state", {method:"PUT", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({who, state})});
  document.getElementById("save").textContent = "✓ enregistré";
  setTimeout(()=>{document.getElementById("save").textContent="—";},1500);
}

function ensureWho(){
  if (who) { document.getElementById("whoBadge").textContent="👤 "+who; return; }
  who = prompt("Ton prénom (pour l'historique) : Arnaud ou Charles ?", "Arnaud") || "Invité";
  localStorage.setItem("kanban_who", who);
  document.getElementById("whoBadge").textContent="👤 "+who;
}

function render(){
  const root = document.getElementById("boards");
  root.innerHTML = "";
  for (const [bk, b] of Object.entries(state.boards)) {
    const bd = document.createElement("div"); bd.className="board";
    const h = document.createElement("h2");
    h.innerHTML = `<span class="dot"></span>${esc(b.name)}`;
    const ai = document.createElement("button"); ai.className="btn"; ai.textContent="✨ IA";
    ai.style.marginLeft="auto"; ai.onclick=()=>suggest(bk);
    h.appendChild(ai); bd.appendChild(h);
    const cols = document.createElement("div"); cols.className="cols";
    for (const ck of COLS) {
      const col = document.createElement("div"); col.className="col "+ck; col.dataset.board=bk; col.dataset.col=ck;
      col.innerHTML = `<h3><span class="k">${LABELS[ck]}</span><span class="mut">${(b.columns[ck]||[]).length}</span></h3>`;
      col.addEventListener("dragover", e=>{e.preventDefault();col.classList.add("drop");});
      col.addEventListener("dragleave", ()=>col.classList.remove("drop"));
      col.addEventListener("drop", e=>{e.preventDefault();col.classList.remove("drop");onDrop(bk,ck);});
      (b.columns[ck]||[]).forEach(c=>col.appendChild(cardEl(bk,ck,c)));
      const add=document.createElement("button"); add.className="add"; add.textContent="+ Ajouter une carte";
      add.onclick=()=>addCard(bk,ck); col.appendChild(add);
      cols.appendChild(col);
    }
    bd.appendChild(cols); root.appendChild(bd);
  }
}

function cardEl(bk, ck, c){
  const el = document.createElement("div"); el.className="card "+ck; el.draggable=true;
  el.innerHTML = `<div class="t">${esc(c.title)}</div>` +
    (c.desc?`<div class="d">${esc(c.desc)}</div>`:``) +
    `<div class="r"><span class="chip">${esc(c.tag||"")}</span><button class="x" title="Supprimer">✕</button></div>`;
  el.addEventListener("dragstart", ()=>{dragging={board:bk,col:ck,id:c.id};busy=true;});
  el.addEventListener("dragend", ()=>{busy=false;});
  el.querySelector(".t").onclick=()=>editCard(bk,ck,c.id);
  el.querySelector(".x").onclick=(e)=>{e.stopPropagation();delCard(bk,ck,c.id);};
  return el;
}

function findCard(bk,ck,id){const a=state.boards[bk].columns[ck];const i=a.findIndex(c=>c.id===id);return [a,i];}

function onDrop(tb, tc){
  if(!dragging) return;
  const {board,col,id}=dragging;
  const [src,i]=findCard(board,col,id); if(i<0){dragging=null;return;}
  const [card]=src.splice(i,1);
  state.boards[tb].columns[tc].push(card);
  dragging=null; render(); push();
}

function newId(){return Math.random().toString(16).slice(2,10);}

function addCard(bk,ck){
  const title=prompt("Titre de la carte :"); if(!title) return;
  const desc=prompt("Détail (optionnel) :","")||"";
  state.boards[bk].columns[ck].push({id:newId(),title,desc,tag:""});
  render(); push();
}

function editCard(bk,ck,id){
  const [a,i]=findCard(bk,ck,id); if(i<0) return; const c=a[i];
  const title=prompt("Titre :",c.title); if(title===null) return; c.title=title||c.title;
  const desc=prompt("Détail :",c.desc||""); if(desc!==null) c.desc=desc;
  const tag=prompt("Étiquette (ia, infra, produit, dev…) :",c.tag||""); if(tag!==null) c.tag=tag;
  render(); push();
}

function delCard(bk,ck,id){
  const [a,i]=findCard(bk,ck,id); if(i<0) return;
  if(!confirm("Supprimer « "+a[i].title+" » ?")) return;
  a.splice(i,1); render(); push();
}

async function suggest(bk){
  const b=state.boards[bk];
  const cards=[]; for(const ck of COLS) (b.columns[ck]||[]).forEach(c=>cards.push([c.title,ck]));
  toast("✨ L'IA réfléchit…");
  const res=await api("/api/ai/suggest",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({board_name:b.name,cards,context:window.__gitctx||""})});
  if(!res.ok && (!res.cards||!res.cards.length)){ toast(res.error||"IA indisponible"); return; }
  showSuggestions(bk,res.cards||[]);
}

function showSuggestions(bk,cards){
  const dlg=document.createElement("dialog");
  dlg.innerHTML=`<h3 style="margin-top:0">✨ Idées IA — ${esc(state.boards[bk].name)}</h3>`;
  if(!cards.length) dlg.innerHTML+=`<p class="mut">Aucune idée retournée.</p>`;
  cards.forEach(c=>{
    const d=document.createElement("div"); d.className="sugg";
    d.innerHTML=`<div class="t">${esc(c.title)}</div><div class="d mut">${esc(c.desc||"")}</div>
      <div class="row"><span class="chip">${LABELS[c.column]||"À faire"}</span></div>`;
    const add=document.createElement("button"); add.className="btn p"; add.textContent="+ Ajouter"; add.style.marginTop="6px";
    add.onclick=()=>{const col=COLS.includes(c.column)?c.column:"todo";
      state.boards[bk].columns[col].push({id:newId(),title:c.title,desc:c.desc||"",tag:"ia"});
      d.style.opacity=.4; add.disabled=true; render(); push();};
    d.appendChild(add); dlg.appendChild(d);
  });
  const close=document.createElement("button"); close.className="btn"; close.textContent="Fermer";
  close.onclick=()=>dlg.close(); dlg.appendChild(close);
  document.body.appendChild(dlg); dlg.showModal(); dlg.addEventListener("close",()=>dlg.remove());
}

async function loadHist(){
  const h=await api("/api/history"); const box=document.getElementById("hist");
  const ic={ajout:"➕",déplacé:"↔️",supprimé:"🗑️"};
  box.innerHTML = h.length? "" : '<p class="mut">Aucune activité pour le moment.</p>';
  h.forEach(e=>{const d=document.createElement("div");d.className="h-item";
    d.innerHTML=`<div>${ic[e.action]||"•"} <b>${esc(e.who)}</b> — ${esc(e.action)} « ${esc(e.title)} »</div>
      <div class="m">${esc(e.detail||"")} · ${esc((e.ts||"").replace("T"," "))}</div>`;
    box.appendChild(d);});
}

document.getElementById("histBtn").onclick=()=>{
  const dr=document.getElementById("drawer"); dr.classList.toggle("open");
  if(dr.classList.contains("open")) loadHist();
};
document.getElementById("aiAll").onclick=()=>suggest(Object.keys(state.boards)[0]);

(async function init(){
  ensureWho();
  await pull(true);
  setInterval(()=>pull(false), 5000);
})();
