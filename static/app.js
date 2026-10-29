'use strict';

const icons = {
  chat:'<path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z"/>',
  folder:'<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
  layers:'<path d="m12 3 9 5-9 5-9-5 9-5zM3 12l9 5 9-5M3 16l9 5 9-5"/>',
  settings:'<path d="M4 7h16M4 17h16M8 4v6M16 14v6"/>',
  download:'<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
  refresh:'<path d="M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-2l2 2M4 17l2 2a7 7 0 0 0 12-2"/>',
  lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4"/>',
  reply:'<path d="m9 10-5 5 5 5M4 15h11a5 5 0 0 0 0-10h-3"/>',
  sparkles:'<path d="m12 3 2.7 6.3L21 12l-6.3 2.7L12 21l-2.7-6.3L3 12l6.3-2.7L12 3zM20 2v4M18 4h4"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  arrowUp:'<path d="M12 19V5m-6 6 6-6 6 6"/>',
  arrowRight:'<path d="M5 12h14m-6-6 6 6-6 6"/>',
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  close:'<path d="m6 6 12 12M6 18 18 6"/>',
  upload:'<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 8l5-5 5 5M12 3v12"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  trash:'<path d="M3 6h18M8 6V3h8v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>',
  file:'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zM14 2v6h6M8 13h8M8 17h5"/>',
  mail:'<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 5-10 8L2 5"/>',
  note:'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zM14 2v6h6M8 13h8M8 17h8"/>',
  copy:'<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
  person:'<circle cx="12" cy="8" r="3"/><path d="M5 21v-3a7 7 0 0 1 14 0v3"/>'
};
const $ = id => document.getElementById(id);
const kindNames = {document:'문서',email:'메일',chat:'챗',note:'메모'};
const kindIcons = {document:'file',email:'mail',chat:'chat',note:'note'};
const state = {coverageByMessage:{},projects:[],project:null,sources:[],conversations:[],messages:[],conversation:null,tab:'chat',mode:'reply',filter:'all',csrf:'',connection:null,busy:false,contextDrafts:{},contextDirty:false,sourceDialogProject:null,viewer:null,preview:null};
let toastTimer;
let selectedFile = null;
let projectLoadSequence = 0;
let conversationLoadSequence = 0;

function icon(name) {
  const wrap = document.createElement('span');
  wrap.setAttribute('aria-hidden','true');
  // Icon markup comes only from the constant table above, never from stored content.
  wrap.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${icons[name] || icons.file}</svg>`;
  return wrap;
}
function el(tag,className,text) { const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=text;return node; }
function storageGet(key,fallback=null) { try{return localStorage.getItem(key)||fallback;}catch{return fallback;} }
function storageSet(key,value) { try{localStorage.setItem(key,value);}catch{} }
function draftKey(projectId) {return `project-desk:draft:${projectId}`;}
function showToast(message,error=false) { clearTimeout(toastTimer);$('toast').textContent=message;$('toast').classList.toggle('error',error);$('toast').hidden=false;toastTimer=setTimeout(()=>$('toast').hidden=true,error?7000:3300); }
function showFormError(id,message) {$(id).textContent=message;$(id).hidden=!message;}
function formatDate(value,withTime=false) {if(!value)return '날짜 미지정';const date=new Date(value.length===10?`${value}T12:00:00`:value);if(Number.isNaN(date.getTime()))return String(value);return new Intl.DateTimeFormat('ko-KR',{month:'long',day:'numeric',...(withTime?{hour:'2-digit',minute:'2-digit'}:{year:'numeric'})}).format(date);}
function setIcons() {document.querySelectorAll('[data-icon]').forEach(node=>{node.replaceChildren(icon(node.dataset.icon));});}
function projectPath(id=state.project?.id) {return `/api/projects/${encodeURIComponent(id)}`;}

async function api(path,options={}) {
  const init={...options,headers:{...options.headers}};
  if(options.body!==undefined){init.body=JSON.stringify(options.body);init.headers['Content-Type']='application/json';}
  if(init.method && !['GET','HEAD'].includes(init.method.toUpperCase()))init.headers['X-CSRF-Token']=state.csrf;
  let response;
  try{response=await fetch(path,init);}catch{throw new Error('앱에 연결할 수 없어요. 실행 창이 열려 있는지 확인해주세요.');}
  let payload;
  try{payload=await response.json();}catch{throw new Error('서버 응답을 읽지 못했어요. 앱을 새로고침해주세요.');}
  if(!response.ok)throw new Error(payload.error||'요청을 처리하지 못했어요. 잠시 뒤 다시 시도해주세요.');
  return payload;
}

function renderProjects() {
  const list=$('project-list');list.replaceChildren();
  state.projects.forEach((project,index)=>{
    const button=el('button',`project-button${project.id===state.project?.id?' active':''}`);button.type='button';button.disabled=state.busy;button.title=project.name;button.setAttribute('aria-label',`${project.name} 선택`);button.setAttribute('aria-current',project.id===state.project?.id?'true':'false');
    button.append(el('span','project-tile',String(index+1).padStart(2,'0')));
    const copy=el('span','project-button-copy');copy.append(el('strong','',project.name),el('small','',`자료 ${project.source_count||0}개 · 독립된 맥락`));button.append(copy);
    if(project.id===state.project?.id)button.append(el('span','project-active-dot'));
    button.addEventListener('click',()=>{if(!state.busy)loadProject(project.id).catch(handleError);});list.append(button);
  });
}
function renderHeading() {
  if(!state.project)return;
  $('project-title').textContent=state.project.name;$('breadcrumb-project').textContent=state.project.name;
  $('project-description').textContent=state.project.description||'자료를 모으고, 흐름을 읽고, 다음 답장을 준비하세요.';
  const index=state.projects.findIndex(p=>p.id===state.project.id);$('project-number').textContent=String(index+1).padStart(2,'0');
  $('source-count').textContent=state.sources.length;
  document.title=`${state.project.name} · 과제노트`;
}
function renderConnection(connection) {
  state.connection=connection;const ready=Boolean(connection?.available&&connection?.authenticated);
  $('connection-dot').className=`status-dot ${ready?'connected':'disconnected'}`;
  $('connection-title').textContent=ready?'ChatGPT 구독 연결됨':'ChatGPT 연결 필요';
  $('connection-detail').textContent=ready?'Codex · 구독 사용량으로 실행':(connection?.message||'연결 상태를 눌러 확인하세요');
  $('refresh-connection').title=connection?.message||'연결 상태 다시 확인';updateComposer();
}
function renderConversations() {
  const list=$('conversation-list');list.replaceChildren();$('conversation-count').textContent=state.conversations.length;
  if(!state.conversations.length){list.append(el('p','no-conversations','새로운 대화가 여기에 쌓여요.\n이 과제의 이야기를 시작해보세요.'));return;}
  state.conversations.forEach(conversation=>{
    const button=el('button',`conversation-button${conversation.id===state.conversation?.id?' active':''}`);button.type='button';button.disabled=state.busy;button.title=conversation.title||'새 대화';button.append(icon('chat'),el('span','',conversation.title||'새 대화'));
    button.addEventListener('click',()=>{if(!state.busy)loadConversation(conversation.id).catch(handleError);});list.append(button);
  });
}
function setTab(tab) {
  state.tab=tab;document.querySelectorAll('[data-tab]').forEach(button=>{const active=button.dataset.tab===tab;button.classList.toggle('active',active);button.setAttribute('aria-selected',String(active));});
  ['chat','sources','context'].forEach(name=>$(name+'-panel').hidden=name!==tab);
}
function setMode(mode) {
  state.mode=mode;document.querySelectorAll('[data-mode]').forEach(button=>button.classList.toggle('selected',button.dataset.mode===mode));
  $('message-input').placeholder=mode==='reply'?'새로 받은 메일이나 챗을 붙여넣으세요. 원하는 답장 방향도 함께 적어주세요.':'진행 상황, 이전 결정, 다음 할 일 등 이 과제에 대해 궁금한 것을 물어보세요.';
}
function updateComposer() {
  const ready=Boolean(state.project&&state.connection?.available&&state.connection?.authenticated);
  $('send-message').disabled=state.busy||!ready||!$('message-input').value.trim();
  $('send-message').setAttribute('aria-label',state.busy?'답변을 준비하고 있어요':'메시지 보내기');
  $('new-conversation').disabled=state.busy||!state.project;
  $('summarize-context').disabled=state.busy||!ready||!state.sources.length;
  $('summarize-context').title=!state.sources.length?'자료를 추가하면 AI로 정리할 수 있어요':'';
  $('composer-note').textContent=state.busy?'이 과제의 맥락을 살펴보고 있어요. 잠시만 기다려주세요.':(!ready?'ChatGPT 연결을 확인해주세요. 자료 저장과 맥락 편집은 계속 사용할 수 있어요.':'답변에 필요한 내용은 OpenAI로 전송됩니다. 초안을 확인한 뒤 직접 보내세요.');
  document.querySelectorAll('[data-mode]').forEach(button=>button.disabled=state.busy);
}
function setBusy(busy) {state.busy=busy;document.body.setAttribute('aria-busy',String(busy));renderProjects();renderConversations();updateComposer();}

function renderWelcome() {
  const welcome=el('div','welcome');const symbol=el('div','welcome-symbol');symbol.append(icon('sparkles'));welcome.append(symbol,el('h2','','오늘의 업무, 함께 정리해볼까요?'));
  welcome.append(el('p','',state.sources.length?'이 과제의 자료와 저장된 맥락을 바탕으로 생각을 이어갑니다.\n새 메시지를 붙여넣거나 궁금한 점을 물어보세요.':'사업계획서, 메일, 대화를 모으면 이 과제만의 맥락이 만들어져요.\n새 메시지에 어떻게 답할지, 다음에 무엇을 해야 할지 함께 살펴보세요.'));
  if(!state.sources.length){const add=el('button','welcome-source-callout');add.type='button';const calloutIcon=el('span','source-callout-icon');calloutIcon.append(icon('folder'));const copy=el('span');copy.append(el('strong','','첫 자료를 추가해보세요'),el('small','','메일 붙여넣기부터 사업계획서 파일까지'));add.append(calloutIcon,copy,icon('arrowRight'));add.addEventListener('click',openSourceDialog);welcome.append(add);}
  const suggestions=el('div','suggestions');
  [{title:'받은 메시지에 답장 쓰기',desc:'상황과 이전 대화를 참고한 답장 초안',icon:'reply',mode:'reply',prompt:''},{title:'지금까지의 흐름 파악하기',desc:'진행 상황과 주요 결정, 남은 질문 정리',icon:'layers',mode:'chat',prompt:'이 과제의 자료와 저장된 맥락을 바탕으로 지금까지의 진행 흐름, 주요 결정 사항, 아직 확인이 필요한 내용을 정리해줘.'},{title:'다음에 할 일 확인하기',desc:'다가오는 일정과 내가 챙길 일',icon:'check',mode:'chat',prompt:'이 과제에서 내가 다음에 해야 할 일과 다가오는 일정을 근거와 함께 정리해줘. 확인되지 않은 일정은 구분해줘.'},{title:'내가 약속한 일 찾아보기',desc:'메일과 대화 속 내 역할과 약속 확인',icon:'search',mode:'chat',prompt:'자료와 저장된 맥락에서 내가 맡기로 했거나 약속한 일을 찾아줘. 담당자가 불분명하면 추정하지 말고 확인이 필요하다고 알려줘.'}].forEach(item=>{const button=el('button','suggestion');button.type='button';const copy=el('span');copy.append(el('strong','',item.title),el('small','',item.desc));button.append(icon(item.icon),copy);button.addEventListener('click',()=>{setMode(item.mode);$('message-input').value=item.prompt;persistDraft();updateComposer();$('message-input').focus();});suggestions.append(button);});
  welcome.append(suggestions);return welcome;
}
function renderInline(node,text) {
  const pattern=/(\*\*([^*]+)\*\*|`([^`]+)`)/g;let last=0,match;
  while((match=pattern.exec(text))!==null){if(match.index>last)node.append(document.createTextNode(text.slice(last,match.index)));node.append(el(match[2]?'strong':'code','',match[2]||match[3]));last=pattern.lastIndex;}
  if(last<text.length)node.append(document.createTextNode(text.slice(last)));
}
function renderMarkdown(target,text) {
  target.replaceChildren();const lines=String(text||'').replace(/\r\n/g,'\n').split('\n');let paragraph=[],list=null,quote=[],fenced=false,code=[];
  function flushParagraph(){if(paragraph.length){const p=el('p');renderInline(p,paragraph.join('\n'));target.append(p);paragraph=[];}}
  function flushQuote(){if(quote.length){const q=el('blockquote');renderInline(q,quote.join('\n'));target.append(q);quote=[];}}
  function reset(){flushParagraph();flushQuote();list=null;}
  for(const line of lines){
    if(/^\s*```/.test(line)){reset();if(fenced){const pre=el('pre');pre.append(el('code','',code.join('\n')));target.append(pre);code=[];}fenced=!fenced;continue;}
    if(fenced){code.push(line);continue;}
    if(!line.trim()){reset();continue;}
    const heading=line.match(/^#{1,6}\s+(.+)$/);if(heading){reset();const count=line.match(/^#+/)[0].length;const h=el(count<3?'h3':'h4');renderInline(h,heading[1]);target.append(h);continue;}
    if(/^\s*([-*_])\1\1+\s*$/.test(line)){reset();target.append(el('hr'));continue;}
    const bullet=line.match(/^\s*([-*+]\s+|\d+[.)]\s+)(.*)$/);if(bullet){flushParagraph();flushQuote();const ordered=/^\d/.test(bullet[1]);if(!list||list.tagName!==(ordered?'OL':'UL')){list=el(ordered?'ol':'ul');target.append(list);}const li=el('li');renderInline(li,bullet[2]);list.append(li);continue;}
    if(/^>\s?/.test(line)){flushParagraph();list=null;quote.push(line.replace(/^>\s?/,''));continue;}
    flushQuote();list=null;paragraph.push(line);
  }
  reset();if(code.length){const pre=el('pre');pre.append(el('code','',code.join('\n')));target.append(pre);}
}
function renderMessages(scroll=true) {
  const container=$('messages');container.replaceChildren();
  if(!state.messages.length)container.append(renderWelcome());
  state.messages.forEach(message=>{
    const role=message.role==='user'?'user':'assistant';const article=el('article',`message ${role}`);const label=el('div','message-label');
    const avatar=el('span','message-avatar');avatar.append(icon(role==='user'?'person':'sparkles'));label.append(avatar,el('span','',role==='user'?'나':'과제노트'),el('time','message-time',formatDate(message.created_at,true)));article.append(label);
    const body=el('div',`message-body ${role==='assistant'?'markdown':''}`);if(role==='user')body.textContent=message.content;else renderMarkdown(body,message.content);article.append(body);
    if(role==='assistant'){
      if(message.references?.length){const refs=el('div','reference-list');refs.append(el('span','reference-label','참고한 자료'));message.references.forEach(reference=>{const button=el('button','reference-button');button.type='button';button.title=`${reference.title}${reference.date?' · '+reference.date:''}`;button.append(icon(kindIcons[reference.kind]||'file'),el('span','',reference.title||'자료 원문'));button.addEventListener('click',()=>openSourceViewer(reference.id).catch(handleError));refs.append(button);});article.append(refs);}
      const coverage=message.coverage||state.coverageByMessage[message.id];if(coverage?.partial)article.append(el('p','retrieval-note',`자료가 많아 관련 부분을 골라 참고했습니다. 전체 ${coverage.total_sources||state.sources.length}개 중 ${coverage.selected_sources||message.references?.length||0}개 자료의 일부를 살펴봤어요.`));
      const actions=el('div','message-actions');const copy=el('button','copy-button');copy.type='button';copy.append(icon('copy'),el('span','','답변 복사'));copy.addEventListener('click',()=>copyText(message.content));actions.append(copy);article.append(actions);
    }
    container.append(article);
  });
  if(state.busy&&state.tab==='chat'){const working=el('div','working-message');working.append(el('span','spinner'),el('span','','자료와 맥락을 살펴보고 있어요…'));container.append(working);}
  if(scroll)requestAnimationFrame(()=>{$('chat-scroll').scrollTop=$('chat-scroll').scrollHeight;});
}
async function copyText(text) {
  try{await navigator.clipboard.writeText(text);showToast('클립보드에 복사했어요.');}
  catch{const input=el('textarea');input.value=text;input.style.position='fixed';input.style.opacity='0';document.body.append(input);input.select();const copied=document.execCommand('copy');input.remove();showToast(copied?'클립보드에 복사했어요.':'복사하지 못했어요. 텍스트를 직접 선택해주세요.',!copied);}
}
function renderSources() {
  const list=$('sources-list');list.replaceChildren();const search=$('source-search').value.trim().toLowerCase();const filtered=state.sources.filter(source=>(state.filter==='all'||source.kind===state.filter)&&(!search||source.title.toLowerCase().includes(search)||(source.filename||'').toLowerCase().includes(search)));
  if(!filtered.length){const empty=el('div','empty-state');const symbol=el('div','empty-state-icon');symbol.append(icon(search||state.filter!=='all'?'search':'folder'));empty.append(symbol,el('h3','',state.sources.length?'조건에 맞는 자료가 없어요':'아직 모아둔 자료가 없어요'),el('p','',state.sources.length?'다른 검색어나 자료 종류로 찾아보세요.':'사업계획서, 메일, 챗 기록을 추가해주세요.\n이 과제의 모든 답변을 뒷받침하는 근거가 됩니다.'));if(!state.sources.length){const add=el('button','primary-button','첫 자료 추가하기');add.type='button';add.addEventListener('click',openSourceDialog);empty.append(add);}list.append(empty);return;}
  filtered.forEach(source=>{const card=el('button','source-card');card.type='button';card.dataset.kind=source.kind;const top=el('div','source-card-top');const symbol=el('span','source-kind-icon');symbol.append(icon(kindIcons[source.kind]||'file'));top.append(symbol,el('span','kind-label',kindNames[source.kind]||'자료'));card.append(top,el('h3','',source.title));if(source.filename)card.append(el('div','source-file-name',source.filename));const footer=el('div','source-card-bottom');footer.append(el('span','',formatDate(source.date||source.created_at)),el('span','',`${Number(source.char_count||0).toLocaleString()}자`));card.append(footer);card.addEventListener('click',()=>openSourceViewer(source.id).catch(handleError));list.append(card);});
}
function renderContext() {
  if(!state.project)return;const hasDraft=Object.prototype.hasOwnProperty.call(state.contextDrafts,state.project.id);
  $('context-input').value=hasDraft?state.contextDrafts[state.project.id]:(state.project.context||'');
  state.contextDirty=$('context-input').value!==(state.project.context||'');
  $('context-save-state').textContent=state.contextDirty?'저장하지 않은 수정 사항이 있어요':(state.project.context?'저장된 맥락을 사용하고 있어요':'아직 저장된 맥락이 없어요');
}
function persistDraft() {if(state.project)storageSet(draftKey(state.project.id),$('message-input').value);}
function mergeProject(project) {const index=state.projects.findIndex(p=>p.id===project.id);if(index>=0)state.projects[index]={...state.projects[index],...project};else state.projects.push(project);if(state.project?.id===project.id)state.project={...state.project,...project};}
async function loadProject(id) {
  if(state.busy)return;const sequence=++projectLoadSequence;++conversationLoadSequence;if(state.project){persistDraft();if(state.contextDirty)state.contextDrafts[state.project.id]=$('context-input').value;}
  const data=await api(projectPath(id));if(sequence!==projectLoadSequence)return;state.project=data.project;mergeProject(data.project);state.sources=data.sources||[];state.conversations=data.conversations||[];state.messages=[];state.conversation=null;state.filter='all';$('source-search').value='';
  document.querySelectorAll('[data-filter]').forEach(button=>button.classList.toggle('selected',button.dataset.filter==='all'));
  storageSet('project-desk:project',id);$('message-input').value=storageGet(draftKey(id),'');
  renderProjects();renderHeading();renderConversations();renderSources();renderContext();renderMessages();updateComposer();
}
async function refreshProjectData() {
  if(!state.project)return;const projectId=state.project.id;const data=await api(projectPath(projectId));if(state.project?.id!==projectId)return;state.project=data.project;mergeProject(data.project);state.sources=data.sources||[];state.conversations=data.conversations||[];renderProjects();renderHeading();renderConversations();renderSources();updateComposer();
}
async function loadConversation(id) {
  if(state.busy)return;const projectId=state.project?.id;const sequence=++conversationLoadSequence;const data=await api(`${projectPath(projectId)}/conversations/${encodeURIComponent(id)}`);if(state.project?.id!==projectId||sequence!==conversationLoadSequence)return;state.conversation=data.conversation;state.messages=data.messages||[];setTab('chat');renderConversations();renderMessages();
}
async function newConversation() {
  if(state.busy||!state.project)return;try{const data=await api(`${projectPath()}/conversations`,{method:'POST',body:{}});state.conversation=data.conversation;state.messages=[];await refreshProjectData();setTab('chat');renderConversations();renderMessages();$('message-input').focus();}catch(error){handleError(error);}
}
async function pollJob(id) {
  const deadline=Date.now()+5*60*1000;
  while(Date.now()<deadline){const job=await api(`/api/jobs/${encodeURIComponent(id)}`);if(job.status==='completed')return job.result||{};if(job.status==='failed')throw new Error(job.error||'답변을 생성하지 못했어요. 연결 상태를 확인하고 다시 시도해주세요.');await new Promise(resolve=>setTimeout(resolve,1100));}
  throw new Error('처리가 오래 걸리고 있어요. 잠시 후 대화 목록에서 결과를 확인해주세요.');
}
async function sendMessage() {
  if(state.busy||!state.project)return;const message=$('message-input').value.trim();if(!message)return;
  const projectId=state.project.id;setBusy(true);setTab('chat');
  try{
    const data=await api(`${projectPath(projectId)}/ask`,{method:'POST',body:{conversation_id:state.conversation?.id||undefined,message,mode:state.mode}});
    $('message-input').value='';persistDraft();
    if(data.conversation_id){const conversationData=await api(`${projectPath(projectId)}/conversations/${encodeURIComponent(data.conversation_id)}`);state.conversation=conversationData.conversation;state.messages=conversationData.messages||[];}else state.messages.push({role:'user',content:message,created_at:new Date().toISOString()});
    renderMessages();const result=await pollJob(data.job_id);
    if(result.message?.id&&result.coverage)state.coverageByMessage[result.message.id]=result.coverage;
    const conversationId=result.conversation_id||data.conversation_id;
    if(conversationId){const conversationData=await api(`${projectPath(projectId)}/conversations/${encodeURIComponent(conversationId)}`);state.conversation=conversationData.conversation;state.messages=conversationData.messages||[];}else if(result.message)state.messages.push(result.message);
    await refreshProjectData();
  }catch(error){handleError(error);if(state.conversation){try{const data=await api(`${projectPath(projectId)}/conversations/${encodeURIComponent(state.conversation.id)}`);state.messages=data.messages||[];}catch{}}}
  finally{setBusy(false);renderMessages();}
}

function openDialog(id) {const dialog=$(id);if(!dialog.open)dialog.showModal();}
function closeDialog(dialog) {dialog.close();}
function openSourceDialog() {
  if(!state.project)return;state.sourceDialogProject=state.project.id;$('source-form').reset();selectedFile=null;$('source-dialog-project').textContent=`${state.project.name}에 저장합니다.`;$('file-label').textContent='파일을 끌어놓거나 선택하세요';$('remove-file').hidden=true;showFormError('source-form-error','');openDialog('source-dialog');
}
function setFile(file) {
  if(!file)return;if(file.size>20*1024*1024){showFormError('source-form-error','파일은 20MB 이하로 넣어주세요. 큰 문서는 나눠서 추가할 수 있어요.');return;}selectedFile=file;$('file-label').textContent=`${file.name} · ${(file.size/1024).toFixed(0)}KB`;$('remove-file').hidden=false;if(!$('source-title').value.trim())$('source-title').value=file.name.replace(/\.[^.]+$/,'');showFormError('source-form-error','');
}
function fileToBase64(file) {return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('파일을 읽지 못했어요. 다른 파일을 선택해주세요.'));reader.readAsDataURL(file);});}
async function saveSource(event) {
  event.preventDefault();const title=$('source-title').value.trim();const content=$('source-content').value.trim();if(!title){showFormError('source-form-error','자료 제목을 입력해주세요.');return;}if(!content&&!selectedFile){showFormError('source-form-error','내용을 붙여넣거나 파일을 선택해주세요.');return;}
  const projectId=state.sourceDialogProject;const button=$('save-source');button.disabled=true;button.textContent='자료를 저장하고 있어요…';showFormError('source-form-error','');
  try{const payload={title,kind:$('source-kind').value,content,date:$('source-date').value||''};if(selectedFile){payload.filename=selectedFile.name;payload.file_base64=await fileToBase64(selectedFile);}const data=await api(`${projectPath(projectId)}/sources`,{method:'POST',body:payload});closeDialog($('source-dialog'));if(projectId===state.project?.id){await refreshProjectData();if(!state.messages.length)renderMessages(false);}showToast(data.warnings?.length?`저장했어요. ${data.warnings.join(' ')}`:'자료를 저장했어요. 이제 이 과제의 대화에서 참고할 수 있어요.');}
  catch(error){showFormError('source-form-error',error.message);}finally{button.disabled=false;button.textContent='과제에 저장';}
}
async function openSourceViewer(id) {
  const projectId=state.project?.id;if(!projectId)return;const data=await api(`${projectPath(projectId)}/sources/${encodeURIComponent(id)}`);if(state.project?.id!==projectId)return;const source=data.source;state.viewer={projectId,source};$('viewer-title').textContent=source.title;$('viewer-kind').textContent=`${kindNames[source.kind]||'자료'} 원문`;$('viewer-meta').textContent=[source.date?`원문 ${formatDate(source.date)}`:'원문 날짜 미지정',source.filename,`${Number(source.char_count||source.content?.length||0).toLocaleString()}자`].filter(Boolean).join(' · ');$('viewer-content').textContent=source.content||'';$('delete-source').disabled=false;openDialog('viewer-dialog');
}
async function deleteSource() {
  const viewer=state.viewer;if(!viewer)return;if(!confirm(`“${viewer.source.title}” 자료를 삭제할까요?\n저장된 대화와 과제 맥락은 그대로 남습니다.`))return;
  $('delete-source').disabled=true;try{await api(`${projectPath(viewer.projectId)}/sources/${encodeURIComponent(viewer.source.id)}`,{method:'DELETE'});closeDialog($('viewer-dialog'));if(viewer.projectId===state.project?.id){await refreshProjectData();if(!state.messages.length)renderMessages(false);}showToast('자료를 삭제했어요.');}catch(error){handleError(error);}finally{$('delete-source').disabled=false;}
}
async function saveContext(content=$('context-input').value) {
  if(!state.project)return;const projectId=state.project.id;$('save-context').disabled=true;
  try{const data=await api(projectPath(projectId),{method:'PATCH',body:{context:content}});mergeProject(data.project);delete state.contextDrafts[projectId];renderContext();showToast('과제 맥락을 저장했어요. 다음 질문부터 참고합니다.');return true;}catch(error){handleError(error);return false;}finally{$('save-context').disabled=false;}
}
async function summarizeContext() {
  if(state.busy||!state.project)return;if(state.contextDirty){showToast('직접 수정한 맥락을 먼저 저장해주세요.',true);return;}
  const projectId=state.project.id;setBusy(true);const button=$('summarize-context');const original=button.textContent;button.textContent='맥락을 정리하고 있어요…';
  try{const data=await api(`${projectPath(projectId)}/summarize`,{method:'POST',body:{}});const result=await pollJob(data.job_id);if(!result.context?.trim())throw new Error('정리된 내용이 없어요. 자료를 확인해주세요.');state.preview={projectId,content:result.context};renderMarkdown($('context-preview'),result.context);if(result.coverage?.partial)$('context-preview').prepend(el('p','retrieval-note','자료가 많아 관련 부분을 골라 정리했습니다. 원문과 날짜를 함께 확인해주세요.'));openDialog('context-preview-dialog');}
  catch(error){handleError(error);}finally{button.replaceChildren(icon('sparkles'),document.createTextNode(' AI로 맥락 정리'));setBusy(false);}
}
async function applyContext() {if(!state.preview||state.preview.projectId!==state.project?.id)return;$('apply-context').disabled=true;try{if(await saveContext(state.preview.content))closeDialog($('context-preview-dialog'));}finally{$('apply-context').disabled=false;}}
function openSettings() {if(!state.project)return;$('settings-name').value=state.project.name;$('settings-description').value=state.project.description||'';showFormError('settings-error','');openDialog('settings-dialog');}
async function saveSettings(event) {event.preventDefault();const name=$('settings-name').value.trim();if(!name){showFormError('settings-error','과제 이름을 입력해주세요.');return;}const button=event.submitter;button.disabled=true;try{const data=await api(projectPath(),{method:'PATCH',body:{name,description:$('settings-description').value.trim()}});mergeProject(data.project);renderProjects();renderHeading();closeDialog($('settings-dialog'));showToast('과제 정보를 저장했어요.');}catch(error){showFormError('settings-error',error.message);}finally{button.disabled=false;}}
function handleError(error) {showToast(error?.message||'처리 중 문제가 생겼어요. 다시 시도해주세요.',true);}
async function refreshConnection() {$('refresh-connection').disabled=true;try{const data=await api('/api/connection');renderConnection(data.connection||data);showToast(state.connection?.message||(state.connection?.authenticated?'ChatGPT 연결을 확인했어요.':'연결 상태를 확인해주세요.'));}catch(error){handleError(error);}finally{$('refresh-connection').disabled=false;}}
function exportProject() {if(!state.project)return;const link=el('a');link.href=`${projectPath()}/export`;link.download=`${state.project.name}-백업.json`;document.body.append(link);link.click();link.remove();}

function bindEvents() {
  document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>setTab(button.dataset.tab)));
  document.querySelectorAll('[data-mode]').forEach(button=>button.addEventListener('click',()=>setMode(button.dataset.mode)));
  document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>{state.filter=button.dataset.filter;document.querySelectorAll('[data-filter]').forEach(item=>item.classList.toggle('selected',item===button));renderSources();}));
  document.querySelectorAll('[data-close-dialog]').forEach(button=>button.addEventListener('click',()=>closeDialog(button.closest('dialog'))));
  document.querySelectorAll('dialog').forEach(dialog=>dialog.addEventListener('click',event=>{if(event.target===dialog){const rect=dialog.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)closeDialog(dialog);}}));
  $('message-input').addEventListener('input',()=>{persistDraft();updateComposer();});$('message-input').addEventListener('keydown',event=>{if(event.key==='Enter'&&(event.metaKey||event.ctrlKey)){event.preventDefault();if(!$('send-message').disabled)sendMessage();}});
  $('send-message').addEventListener('click',sendMessage);$('new-conversation').addEventListener('click',newConversation);$('add-source').addEventListener('click',openSourceDialog);$('composer-add-source').addEventListener('click',openSourceDialog);$('source-search').addEventListener('input',renderSources);$('source-form').addEventListener('submit',saveSource);$('source-file').addEventListener('change',()=>setFile($('source-file').files?.[0]));$('remove-file').addEventListener('click',()=>{selectedFile=null;$('source-file').value='';$('file-label').textContent='파일을 끌어놓거나 선택하세요';$('remove-file').hidden=true;});
  const drop=$('file-drop');['dragenter','dragover'].forEach(name=>drop.addEventListener(name,event=>{event.preventDefault();drop.classList.add('dragover');}));['dragleave','drop'].forEach(name=>drop.addEventListener(name,event=>{event.preventDefault();drop.classList.remove('dragover');}));drop.addEventListener('drop',event=>setFile(event.dataTransfer?.files?.[0]));
  $('delete-source').addEventListener('click',deleteSource);$('context-input').addEventListener('input',()=>{if(!state.project)return;state.contextDrafts[state.project.id]=$('context-input').value;state.contextDirty=$('context-input').value!==(state.project.context||'');$('context-save-state').textContent=state.contextDirty?'저장하지 않은 수정 사항이 있어요':'저장된 내용과 같아요';});$('save-context').addEventListener('click',()=>saveContext());$('summarize-context').addEventListener('click',summarizeContext);$('apply-context').addEventListener('click',applyContext);$('project-settings').addEventListener('click',openSettings);$('settings-form').addEventListener('submit',saveSettings);$('refresh-connection').addEventListener('click',refreshConnection);$('export-project').addEventListener('click',exportProject);
  window.addEventListener('beforeunload',event=>{if(state.busy||state.contextDirty){event.preventDefault();event.returnValue='';}});
}
async function init() {
  setIcons();bindEvents();updateComposer();
  try{const data=await api('/api/bootstrap');state.csrf=data.csrf_token;state.projects=data.projects||[];renderConnection(data.connection);if(!state.projects.length)throw new Error('과제를 불러오지 못했어요. 앱을 다시 실행해주세요.');const saved=storageGet('project-desk:project');const project=state.projects.find(p=>p.id===saved)||state.projects[0];await loadProject(project.id);}
  catch(error){$('global-error').textContent=error.message;$('global-error').hidden=false;$('project-title').textContent='앱 연결을 확인해주세요';$('project-description').textContent='실행 창을 확인한 뒤 새로고침해주세요.';}
}
init();
