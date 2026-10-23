"""Reproducible academic figures from committed scores and actual MedDB assets."""
import gzip,hashlib,json,textwrap
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch,FancyArrowPatch
import networkx as nx
ROOT=Path(__file__).resolve().parents[1]
TEAM=ROOT.parent if (ROOT.parent/'meddb/data').exists() else ROOT/'vendor/meddb-publish'
OUT=ROOT/'assets/paper';OUT.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'svg.fonttype':'none','savefig.facecolor':'white','axes.spines.top':False,'axes.spines.right':False})
BLUE='#1f4e79';TEAL='#177e75';ORANGE='#b86b22';GRAY='#536476';RED='#ad4148'

def box(ax,x,y,w,h,label,color=BLUE,fs=10):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.008,rounding_size=0.012',fc='white',ec=color,lw=1.4))
    ax.text(x+w/2,y+h/2,label,ha='center',va='center',fontsize=fs,color='#152b3c',linespacing=1.45)

def arrow(ax,a,b,label='',dashed=False,color=GRAY):
    ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=11,lw=1.15,color=color,linestyle='--' if dashed else '-'))
    if label:ax.text((a[0]+b[0])/2,(a[1]+b[1])/2+.014,label,ha='center',va='bottom',fontsize=8,color=color,bbox={'facecolor':'white','edgecolor':'none','pad':1})

def save(fig,name):
    fig.savefig(OUT/(name+'.svg'),bbox_inches='tight');fig.savefig(OUT/(name+'.png'),dpi=180,bbox_inches='tight');plt.close(fig)

# Fig.1: final reader does NOT feed the B1 next-action model directly.
fig,axes=plt.subplots(1,3,figsize=(16,7.3))
for ax in axes:ax.set_xlim(0,1);ax.set_ylim(0,1);ax.axis('off')
for ax,title in zip(axes,['A  Initial independent harness','B  Experimental extensions','C  Final B1O1 (B1-based)']):ax.text(.02,.97,title,weight='bold',fontsize=12,va='top')
a=axes[0]
for y,label in [(.77,'Patient / examiner API'),(.55,'Evidence + PatientState\npolarity / subject / time'),(.32,'LLM planner + clinical advisor\ncoverage / goals / validator'),(.08,'SOAP builder + closing\nDIAGNOSE submission')]:box(a,.12,y,.76,.13,label)
arrow(a,(.5,.77),(.5,.68),'actual observations');arrow(a,(.5,.55),(.5,.45));arrow(a,(.5,.32),(.5,.21));arrow(a,(.12,.38),(.04,.82),'',True);arrow(a,(.04,.82),(.12,.82),'SAY / EXAM',True)
a=axes[1]
for y,label in [(.77,'E2 consultation / observations'),(.55,'R1 / R2: guideline retrieval\nLSA + SQLite / hybrid ranking'),(.32,'R3: query / selection / generation\nR4: record-stage LangGraph'),(.08,'S1-S3 / observation / Q1\nplan-speech checks; extra calls')]:box(a,.1,y,.8,.13,label,ORANGE)
for y in [.77,.55,.32]:arrow(a,(.5,y),(.5,y-.09),'',True)
a.text(.5,.015,'Separate experiments; not one final stack',ha='center',fontsize=9,color=ORANGE)
a=axes[2]
box(a,.1,.78,.8,.12,'Patient / examiner API',TEAL)
box(a,.1,.57,.8,.13,'B1 next-action LLM\nraw transcript + remaining budget',TEAL)
box(a,.1,.35,.8,.13,'B1O1 Q/A reader + Tracker\nsource pairs; conservative links',TEAL)
box(a,.1,.1,.8,.15,'Ontology SOAP draft + model writer\nB1 closing + actual speech record\nDIAGNOSE',TEAL,9)
arrow(a,(.5,.78),(.5,.7),'raw transcript');arrow(a,(.9,.63),(.98,.63));arrow(a,(.98,.63),(.98,.84));arrow(a,(.98,.84),(.9,.84),'SAY / EXAM')
arrow(a,(.18,.78),(.18,.49),'Q/A',True);arrow(a,(.5,.35),(.5,.26),'KB findings / draft')
a.text(.5,.035,'29-turn intake cap; DONE retained\nNo RAG / LangGraph / extra extraction call',ha='center',fontsize=9,color=TEAL)
fig.subplots_adjust(wspace=.25);save(fig,'fig01_architecture_evolution')

fig,ax=plt.subplots(figsize=(13,6.3));ax.axis('off');ax.set_xlim(0,1);ax.set_ylim(0,1)
ax.text(.02,.95,'Knowledge construction and separation of responsibilities',weight='bold',fontsize=15)
box(ax,.03,.65,.27,.18,'Source / provenance layer\nsource version, locator, review status\nRDF/OWL schema + assertions',BLUE,10)
box(ax,.37,.65,.27,.18,'Clinical authoring layer\ncomplaints / diseases / findings\nexams / slots / plans',TEAL,10)
box(ax,.71,.65,.26,.18,'Validated release / runtime JSON\nreference checks; action length\nlinks, conditions, build hashes',TEAL,10)
arrow(ax,(.3,.74),(.37,.74),'reference');arrow(ax,(.64,.74),(.71,.74),'compile')
box(ax,.08,.26,.32,.19,'Static clinical knowledge\nkey / support / against / rule_out\nexam targets + care plans',TEAL,10)
box(ax,.59,.26,.32,.19,'Encounter observations\nquestion + actual response + turn\nassertion / scope / raw evidence',ORANGE,10)
arrow(ax,(.84,.65),(.24,.45),'clinical runtime subset',True)
arrow(ax,(.4,.355),(.59,.355),'interpretation / candidate support')
box(ax,.32,.04,.37,.11,'SOAP + differential reasoning\nassociation score is not probability',GRAY,10)
arrow(ax,(.24,.26),(.44,.15));arrow(ax,(.75,.26),(.59,.15))
ax.text(.5,.53,'Imported reference graph and clinical runtime are distinct assets; no full OWL reasoner in final agent.',ha='center',fontsize=9,color=GRAY)
save(fig,'fig02_ontology_construction')

D=TEAM/'meddb/data';load=lambda name:json.loads((D/(name+'.json')).read_text())
diseases=load('diseases');complaints=load('complaints');findings=load('findings');exams=load('exams');slots=load('slots')
mi=next(d for d in diseases if d['id']=='mi');cp=next(c for c in complaints if c['id']=='chest_pain')
G=nx.DiGraph();G.add_node('chest_pain',label='Complaint\nChest pain',kind='complaint');G.add_node('mi',label='Disease\nAcute myocardial infarction\nKCD I21.9',kind='disease')
assert 'mi' in cp['diseases'];G.add_edge('chest_pain','mi',relation='candidate')
fl={f['id']:f for f in findings};english={'pressure_chest_pain':'Pressure-like chest pain','radiation_arm_jaw':'Arm / jaw radiation','diaphoresis':'Diaphoresis','dyspnea':'Dyspnea','chest_wall_tenderness':'Chest-wall tenderness'}
for rel,ids in [('key',mi['key'][:3]),('support',['dyspnea']),('against',['chest_wall_tenderness'])]:
 for fid in ids:
  assert fid in mi[rel];G.add_node(fid,label=english[fid],kind='finding');G.add_edge('mi',fid,relation=rel)
eid=cp['exams'][0];G.add_node(eid,label='Physical exam\nHeart auscultation',kind='exam');G.add_edge('chest_pain',eid,relation='exam menu')
pos={'chest_pain':(0,0),'mi':(1.5,.45),eid:(1.5,-1.65),'pressure_chest_pain':(4,1.9),'radiation_arm_jaw':(4,.95),'diaphoresis':(4,0),'dyspnea':(4,-.95),'chest_wall_tenderness':(4,-1.9)}
fig,ax=plt.subplots(figsize=(13,6));ax.axis('off');ax.set_xlim(-.8,5);ax.set_ylim(-2.6,2.65)
ax.text(-.7,2.42,'Observed data graph: clinical runtime subset',fontsize=14,weight='bold')
colors={'complaint':BLUE,'disease':TEAL,'finding':GRAY,'exam':ORANGE}
for u,v,data in G.edges(data=True):
 x,y=pos[u];xx,yy=pos[v];ax.annotate('',(xx-.64,yy),(x+.58,y),arrowprops={'arrowstyle':'-|>','color':GRAY,'lw':1.2,'connectionstyle':'arc3,rad=0'})
 ax.text((x+xx)/2,(y+yy)/2+.06,data['relation'],fontsize=9,ha='center',bbox={'fc':'white','ec':'none','pad':1})
for n,data in G.nodes(data=True):
 x,y=pos[n];ax.text(x,y,data['label'],ha='center',va='center',fontsize=10,bbox={'boxstyle':'round,pad=.5','fc':'white','ec':colors[data['kind']],'lw':1.4})
ax.text(2,-2.47,'Edges are read from complaints.json / diseases.json; draft associations, not verified causal or diagnostic rules.',ha='center',fontsize=9,color=GRAY)
save(fig,'fig03_runtime_ontology_graph')

scores=json.loads((ROOT/'docs/paper/sample_scores.json').read_text());r=scores['rows']
fig,ax=plt.subplots(figsize=(12,8));ys=list(range(len(r)));vals=[x['total'] for x in r]
cs=[TEAL if x['id']=='B1O1' else RED if x['id']=='Q1' else BLUE if x['id']=='R3a' else '#a9b7c4' for x in r]
ax.barh(ys,vals,color=cs,height=.68);ax.set_yticks(ys,[x['id'] for x in r]);ax.invert_yaxis();ax.set_xlim(0,100);ax.set_xlabel('Server sample score / 100')
ax.axvline(77.714,ls='--',color=GRAY,lw=1,label='Historical E2 sample: 77.714')
for y,v in zip(ys,vals):ax.text(v+.8,y,f'{v:.3f}',va='center',fontsize=9)
ax.set_title('Single-batch public-sample observations across development variants',loc='left',pad=15,fontsize=13)
ax.legend(loc='lower right',frameon=False);ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
fig.text(.13,.015,'Three public cases per batch; different execution times and changing code. No confidence intervals or causal attribution.',fontsize=9,color=GRAY)
save(fig,'fig04_sample_results')

q=json.loads((ROOT/'reports/model_questions_final_054.json').read_text())['sessions'];b=json.loads((ROOT/'reports/b1_rebase_sessions_057.json').read_text())['sessions']
fig,axs=plt.subplots(1,2,figsize=(13,4.6));cases=['C01','C03','C10'];series=[('Q1 control',q,'R3a_observation_state',GRAY),('Q1',q,'R3a_model_questions',RED),('B1 control',b,'B1',BLUE),('B1O1',b,'B1O1',TEAL)]
for offset,(label,rows,mode,c) in enumerate(series):
 data={s['case']:s for s in rows if s['mode']==mode}
 for ax,key,scale in [(axs[0],'doctor_attempted_request_ids',1),(axs[1],'prompt_tokens',1000)]:
  ax.bar([i+(offset-1.5)*.18 for i in range(3)],[data[k][key]/scale for k in cases],width=.17,color=c,label=label)
for ax,label in zip(axs,['Doctor request attempts','Reported input tokens (thousands)']):ax.set_xticks(range(3),cases);ax.set_ylabel(label);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
axs[0].legend(fontsize=8,frameon=False,ncol=2);fig.suptitle('Development API cost: separate cohorts and different patient/model trajectories',x=.08,ha='left',fontsize=13)
fig.tight_layout(rect=(0,.05,1,.92));fig.text(.08,.01,'Q1 and B1O1 use different bases. Cost differences are descriptive, not reader-only effects or official efficiency estimates.',fontsize=9,color=GRAY)
save(fig,'fig05_development_cost')

release=TEAM/'data/releases/meddb-2026.10.13.1.json.gz';v=json.loads(gzip.decompress(release.read_bytes()))
stats={'runtime':{n:len(load(n)) for n in ['complaints','diseases','findings','exams','slots']},'disease_finding_relations':{k:sum(len(d.get(k,[])) for d in diseases) for k in ['key','support','against','rule_out']},'reference_release':{'version':v['version'],'concepts':len(v['concepts']),'assertions':len(v['assertions']),'sources':len(v['sources'])},'attribution':'Existing team MedDB assets reused and extended; counts do not imply new author contribution or clinical validation.'}
(ROOT/'docs/paper/ontology_statistics.json').write_text(json.dumps(stats,indent=2)+'\n')
manifest={'scope':'Static academic figures; graph edges from actual runtime files, not patient answer scripts','source_sha256':{str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'docs/paper/sample_scores.json',D/'complaints.json',D/'diseases.json',release]},'artifacts':[p.name for p in sorted(OUT.glob('*')) if p.suffix in ['.svg','.png']]}
(OUT/'figure_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(stats))
