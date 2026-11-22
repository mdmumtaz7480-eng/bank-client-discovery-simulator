const $=id=>document.getElementById(id);
let clients=[],products=[],client=null,history=[];
const show=(sec,step)=>{["pick","interview","rec","feedback"].forEach(s=>$(s).classList.toggle("hidden",s!==sec));
 [1,2,3,4].forEach(i=>$("s"+i).classList.toggle("on",i===step));};
const esc=s=>s.replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
function md(t){ // tiny markdown: ## headings, bullets, **bold**
 let h=esc(t).replace(/^## (.*)$/gm,"<h2>$1</h2>").replace(/\*\*(.+?)\*\*/g,"<b>$1</b>");
 h=h.replace(/(^|\n)((?:[-*] .*(?:\n|$))+)/g,(m,a,l)=>a+"<ul>"+l.trim().split("\n").map(x=>"<li>"+x.replace(/^[-*] /,"")+"</li>").join("")+"</ul>");
 return h.replace(/\n(?!<)/g,"<br>");}
function add(role,text){const d=document.createElement("div");d.className="msg "+role;d.textContent=text;$("chat").appendChild(d);$("chat").scrollTop=1e9;return d;}
async function api(path,body){const r=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
 const j=await r.json();if(!r.ok)throw new Error(j.error||r.statusText);return j;}
async function init(){
 [clients,products]=await Promise.all([fetch("/api/clients").then(r=>r.json()),fetch("/api/products").then(r=>r.json())]);
 const cfg=await fetch("/api/config").then(r=>r.json());$("model").textContent="Model: "+cfg.model;
 $("cards").innerHTML=clients.map(c=>`<div class="card"><div class="avatar">${esc(c.avatar)}</div><h3>${esc(c.name)}</h3><p><i>${esc(c.tagline)}</i></p>
  <p><b>Age:</b> ${c.profile.age} &middot; ${esc(c.profile.location)}</p><p>${esc(c.profile.background)}</p><p>${esc(c.profile.financial_situation)}</p>
  <button data-id="${c.id}">Interview ${esc(c.name.split(" ")[0])}</button></div>`).join("");
 $("cards").querySelectorAll("button").forEach(b=>b.onclick=()=>start(b.dataset.id));
 $("products").innerHTML=products.map(p=>`<div class="prod"><h4>${esc(p.name)} <span class="tag ${p.sharia_compliant?"":"no"}">${p.sharia_compliant?"Sharia-compliant":"Conventional"}</span></h4>
  <div>${esc(p.summary)}</div><b>Features</b><ul>${p.features.map(f=>"<li>"+esc(f)+"</li>").join("")}</ul><b>Limitations</b><ul>${p.limitations.map(f=>"<li>"+esc(f)+"</li>").join("")}</ul></div>`).join("");
}
function start(id){client=clients.find(c=>c.id===id);history=[];$("chat").innerHTML="";
 $("cname").textContent="Interview with "+client.name;$("cintro").textContent=client.profile.stated_need_at_start;
 $("summary").value="";$("recs").value="";show("interview",2);$("msg").focus();}
async function send(){const t=$("msg").value.trim();if(!t)return;$("msg").value="";add("student",t);history.push({role:"student",content:t});
 $("send").disabled=true;const wait=add("client","...");
 try{const {reply}=await api("/api/chat",{client_id:client.id,messages:history});wait.textContent=reply;history.push({role:"client",content:reply});}
 catch(e){wait.textContent="Error: "+e.message;wait.classList.add("err");history.pop();}
 $("send").disabled=false;$("msg").focus();}
$("send").onclick=send;$("msg").onkeydown=e=>{if(e.key==="Enter")send();};
$("toRec").onclick=()=>show("rec",3);$("backInt").onclick=()=>show("interview",2);$("back").onclick=()=>show("pick",1);$("again").onclick=()=>show("pick",1);
$("getFb").onclick=async()=>{$("fbErr").textContent="";if(history.length<2){$("fbErr").textContent="Interview the client first.";return;}
 $("getFb").disabled=true;$("getFb").textContent="Coach is reviewing...";
 try{const {feedback}=await api("/api/feedback",{client_id:client.id,messages:history,summary:$("summary").value,recommendations:$("recs").value});
  $("fbBody").innerHTML=md(feedback);show("feedback",4);}catch(e){$("fbErr").textContent=e.message;}
 $("getFb").disabled=false;$("getFb").textContent="Get coaching feedback";};
init();
