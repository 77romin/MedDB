// Proposed mappings require a deliberate apply action; patient text is never stored.
const agentInputSection=el('section'),agentText=el('textarea'),agentPreview=el('div'),agentNormalizeButton=el('button','표현 해석');
agentText.id='patient-text';agentText.rows=4;agentText.placeholder='환자의 말을 증상별로 한 줄씩 입력하세요.\n열이 없어요\n기침이 있어요';agentText.setAttribute('aria-label','환자 표현');
agentInputSection.append(el('h2','환자 표현에서 소견 찾기'),agentText,agentNormalizeButton,agentPreview);
$('finding-search').before(agentInputSection);
let agentNormalizeRequest=0;
agentText.oninput=()=>{agentNormalizeRequest++;agentPreview.textContent='표현을 해석한 뒤 상태를 확인해 적용하세요.'};
agentNormalizeButton.onclick=async()=>{
 const ticket=++agentNormalizeRequest;agentPreview.textContent='해석 중…';
 try{
  const result=await api('/api/normalize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:agentText.value})});
  if(ticket!==agentNormalizeRequest)return;agentPreview.replaceChildren();const controls=[];
  for(const mention of result.mentions){
   const row=el('div',undefined,'observation'),select=el('select'),finding=el('select');
   mention.candidate_ids.forEach((id,i)=>{const o=el('option',mention.labels[i]);o.value=id;finding.append(o)});
   for(const[state,label]of [['unknown','미확인'],['present','있음'],['absent','없음']]){const o=el('option',label);o.value=state;select.append(o)}
   select.value=mention.proposed_state;select.setAttribute('aria-label',mention.phrase+' 상태');finding.setAttribute('aria-label',mention.phrase+' 개념');
   row.append(el('span',mention.statement),finding,select);agentPreview.append(row);controls.push({finding,select});
   if(mention.reason!=='dictionary_match')agentPreview.append(el('p','부정 범위·과거력·가족력 또는 상충 표현을 확인하세요.','notice'));
   if(mention.duration_mentions.length)agentPreview.append(el('p','기간 표현 보존: '+mention.duration_mentions.join(', ')+' · 현재 점수에는 반영하지 않습니다.','notice'));
  }
  if(result.unmatched.length)agentPreview.append(el('p','매핑하지 못한 표현: '+result.unmatched.join(' / '),'notice'));
  if(!controls.length)return;
  agentPreview.append(el('p','초안 매핑입니다. 소견과 상태를 확인한 뒤 적용하세요.','notice'));
  const apply=el('button','확인한 소견 적용');apply.onclick=()=>{
   if(ticket!==agentNormalizeRequest)return;const proposed=new Map();
   for(const {finding,select}of controls){const id=finding.value;if(!proposed.has(id))proposed.set(id,new Set());proposed.get(id).add(select.value)}
   if([...proposed.values()].some(states=>states.size>1)){agentPreview.append(el('p','같은 소견의 있음·없음이 충돌합니다. 상태를 다시 확인하세요.','notice'));return}
   for(const[id,states]of proposed){const state=[...states][0];if(state==='unknown')observationState.delete(id);else observationState.set(id,state)}
   observations();clearRank();apply.textContent='소견 체크에 적용했습니다';
  };agentPreview.append(apply);
 }catch(e){if(ticket===agentNormalizeRequest)agentPreview.textContent='표현 해석에 실패했습니다. 입력을 확인하세요.'}
};

const agentPolicyLabel=el('label','사용 자료 '),agentPolicySelect=el('select');agentPolicySelect.id='knowledge-profile';
for(const[value,label]of [['research','전체 연구용 초안'],['pilot','복통 파일럿 초안']]){const o=el('option',label);o.value=value;agentPolicySelect.append(o)}
agentPolicyLabel.append(agentPolicySelect);$('rank-draft').parentElement.before(agentPolicyLabel);agentPolicySelect.onchange=clearRank;

const guidelineSection=el('section'),guidelineQuery=el('input'),guidelineButton=el('button','지침 검색'),guidelineResults=el('div');
guidelineQuery.type='search';guidelineQuery.placeholder='불면, 수면제 의존, 성장지연 등';guidelineQuery.setAttribute('aria-label','진료지침 검색어');
guidelineSection.append(el('h2','공식 진료지침 검색'),guidelineQuery,guidelineButton,guidelineResults);$('results').after(guidelineSection);
let guidelineRequest=0;
guidelineButton.onclick=async()=>{
 const ticket=++guidelineRequest;guidelineResults.textContent='검색 중…';
 try{
  const result=await api('/api/guidelines',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:guidelineQuery.value,limit:3})});
  if(ticket!==guidelineRequest)return;guidelineResults.replaceChildren();
  if(!result.available){guidelineResults.textContent='공식 진료지침 경로를 찾지 못했습니다. NOVA_GUIDELINES_DIR 설정을 확인하세요.';return}
  for(const doc of result.documents){const item=el('div',undefined,'candidate');item.append(el('strong',doc.title),el('p',`${doc.organization} · ${doc.year} · ${doc.license}`));
   if(/^https?:\/\//.test(doc.source_url)){const link=el('a','출처 열기');link.href=doc.source_url;link.target='_blank';link.rel='noopener';item.append(link)}
   const excerpt=el('pre',doc.excerpt);excerpt.style.whiteSpace='pre-wrap';item.append(el('p',`${doc.path} · ${doc.start_line}~${doc.end_line}행 · 원문 일부`,'notice'),excerpt);guidelineResults.append(item)}
  if(!result.documents.length)guidelineResults.textContent='제목이 일치하는 지침이 없습니다. 영어명이나 더 구체적인 검색어를 입력하세요.';
 }catch(e){if(ticket===guidelineRequest)guidelineResults.textContent='검색에 실패했습니다. 검색어와 자료 경로를 확인하세요.'}
};

function renderAgentRecommendations(workflow){
 const section=el('section');section.append(el('h2','다음 확인 제안'),el('p',`사용 자료: ${workflow.policy.name} · 관계 ${workflow.policy.assertions.toLocaleString()}개 · 초안 ${workflow.policy.draft.toLocaleString()}개`,'notice'));
 for(const recommendation of workflow.recommendations){
  const row=el('div',undefined,'candidate');row.append(el('strong',recommendation.label));
  row.append(el('p',recommendation.action?`${recommendation.action}: ${recommendation.content}`:'확인 동작 템플릿이 없습니다. 질문·진찰 방법을 검토하세요.'));
  row.append(el('p',`양성 연관 후보 ${recommendation.associated_candidates.length} · 제외 소견 후보 ${recommendation.excluded_candidates.length} · 자료에 관계 없는 후보 ${recommendation.unrecorded_candidates.length}`));
  row.append(el('p','검수 전 제안입니다. 자료에 없는 소견은 음성을 뜻하지 않습니다.','notice'));
  const detail=el('details');detail.append(el('summary','추천의 관계 근거'));
  for(const evidence of recommendation.evidence){const source=sources.get(evidence.source_id),p=el('p',`${source?.title||evidence.source_id} · ${evidence.locator} · ${evidence.context}`);detail.append(p)}
  row.append(detail);section.append(row);
 }
 if(!workflow.recommendations.length)section.append(el('p','현재 후보에서 추가 확인할 소견을 찾지 못했습니다.','sub'));
 for(const item of workflow.checklists||[]){const row=el('div',undefined,'candidate');row.append(el('strong',item.title),el('p',item.content||item.plan),el('p',item.source.url||item.source.path,'notice'));section.append(row)}
 $('results').append(section);
}
