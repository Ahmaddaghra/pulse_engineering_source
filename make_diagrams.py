from pathlib import Path
import subprocess, textwrap
P=Path(__file__).parent/'diagrams'; P.mkdir(exist_ok=True)
HEADER='''graph [bgcolor="transparent",pad="0.20",nodesep="0.48",ranksep="0.60",fontname="Lato",fontsize=11,splines=ortho]; node [shape=box,style="rounded,filled",fontname="Lato",fontsize=10,penwidth=1.2,color="#B9CBDA",fillcolor="#EAF3F7",fontcolor="#17334A",margin="0.20,0.13"]; edge [fontname="Lato",fontsize=9,color="#638299",fontcolor="#46647A",arrowsize=.70,penwidth=1.25];'''
def write(n,source):
 src=P/(n+'.dot'); src.write_text(source)
 subprocess.run(['dot','-Tsvg',str(src),'-o',str(P/(n+'.svg'))],check=True)
 subprocess.run(['dot','-Tpng','-Gdpi=190',str(src),'-o',str(P/(n+'.png'))],check=True)

write('01_context',f'''digraph context {{ {HEADER} rankdir=LR;
 editor [label="Newsroom Editor\\n(review, prioritize)",fillcolor="#D8F0E6",color="#89B9A2"];
 lead [label="Editorial Lead\\n(approve source panel)",fillcolor="#D8F0E6",color="#89B9A2"];
 panel [label="Permitted Publisher Feeds\\n(metadata and timestamps)"];
 trends [label="Search-interest Signals\\n(licensed / public exports)"];
 pulse [label="PULSE\\nEarly-signal intelligence\\n[system under design]",fillcolor="#CCE1F8",color="#3679A0",penwidth=2];
 editor -> pulse [label="inspect ranked evidence"];
 lead -> pulse [label="policies and review"];
 panel -> pulse [label="observations"];
 trends -> pulse [label="optional attention proxy"];
 pulse -> editor [label="alerts and evidence"];
 }}''')
write('02_containers',f'''digraph containers {{ {HEADER} rankdir=TB;
 subgraph cluster_boundary {{label="PULSE application boundary | modular monolith + workers"; color="#A4C2D4"; style="rounded,dashed";
 web [label="Review Web UI\\nReact / TypeScript",fillcolor="#D8F0E6"];
 api [label="Application API\\nFastAPI + RBAC",fillcolor="#CCE1F8"];
 worker [label="Ingestion Worker\\nfetch | validate | deduplicate",fillcolor="#CCE1F8"];
 detect [label="Event Intelligence Worker\\nlink | cluster | version",fillcolor="#CCE1F8"];
 forecast [label="Forecast Worker\\nbaseline | model | rank",fillcolor="#CCE1F8"];
 db [label="PostgreSQL\\nobservations | provenance | outbox",shape=cylinder,fillcolor="#F3E9DA"];
 store [label="Object Store\\nlicensed raw snapshots",shape=cylinder,fillcolor="#F3E9DA"];
 }}
 ext [label="Authorized RSS / Export Sources",fillcolor="#F1F4F6"];
 web -> api; api -> db; ext -> worker; worker -> store; worker -> db; db -> detect; detect -> db; db -> forecast; forecast -> db; api -> forecast [label="read predictions",style=dashed];
 }}''')
write('03_ingestion',f'''digraph ingress {{ {HEADER} rankdir=LR;
 source [label="Publisher RSS\\nallowlisted host"];
 fetch [label="Fetch with conditional GET\\nETag / Last-Modified"];
 audit [label="Store immutable fetch receipt\\nstatus / hash / first-seen UTC"];
 parse [label="Parse safely\\nno DTD / size limits"];
 rights [label="Source policy gate\\nlicense + retention"];
 norm [label="Normalize + canonicalize\\nURL, title, time"];
 dedup [label="Deduplicate\\ncanonical URL + hash"];
 records [label="Persist provenance-linked\\narticle metadata",fillcolor="#D8F0E6"];
 stop [label="Quarantine / disabled\\nno silent fallback",fillcolor="#FBE6E3",color="#D79A91"];
 source -> fetch -> audit -> parse -> rights -> norm -> dedup -> records;
 fetch -> stop [label="429 / invalid",color="#BA716A"];
 parse -> stop [label="malformed",color="#BA716A"];
 rights -> stop [label="prohibited",color="#BA716A"];
 }}''')
write('04_event_state',f'''digraph states {{ {HEADER} rankdir=TB;
 unseen [label="UNSEEN",fillcolor="#F2F5F7"];
 candidate [label="CANDIDATE\\ninitial mentions"];
 active [label="ACTIVE\\nconfirmed event cluster",fillcolor="#D8F0E6"];
 cooling [label="COOLING\\nlow recent activity",fillcolor="#FAEECF"];
 closed [label="CLOSED\\nretained snapshot",fillcolor="#F2F5F7"];
 quarantine [label="QUARANTINED\\nambiguous / unsafe",fillcolor="#FBE6E3"];
 unseen -> candidate [label="first eligible item"];
 candidate -> active [label="cluster validation"];
 candidate -> quarantine [label="uncertain / conflict"];
 active -> cooling [label="inactivity threshold"];
 cooling -> active [label="new eligible mention"];
 cooling -> closed [label="retention window"];
 active -> quarantine [label="merge dispute"];
 quarantine -> active [label="human adjudication"];
 }}''')
write('05_erd',f'''digraph erd {{ {HEADER} rankdir=TB; node [shape=record,style="filled",fontsize=9,margin="0.08,0.08"];
 publisher [label="{{PUBLISHER|publisher_id (PK)\\llegal_owner_id\\lregion; eligible\\l}}",fillcolor="#E1EDF8"];
 feed [label="{{SOURCE_FEED|feed_id (PK)\\lpublisher_id (FK)\\lpolicy_version\\lstatus\\l}}"];
 fetch [label="{{FETCH_RECEIPT|fetch_id (PK)\\lfeed_id (FK)\\lfetched_at; status; hash\\l}}"];
 article [label="{{ARTICLE|article_id (PK)\\lfeed_id (FK)\\lcanonical_url; title_hash\\lpublished_at; first_seen_at\\l}}"];
 event [label="{{EVENT|event_id (PK)\\lcreated_at; state\\lcluster_version\\l}}",fillcolor="#D8F0E6"];
 member [label="{{EVENT_MEMBERSHIP|article_id (FK)\\levent_id (FK)\\lassigned_at; version\\l}}"];
 obs [label="{{OBSERVATION|event_id (FK)\\lcutoff_at; source_panel_id\\lfeatures_hash\\l}}"];
 pred [label="{{PREDICTION|prediction_id (PK)\\lcutoff_at; event_id (FK)\\lmodel_version; probability\\l}}",fillcolor="#FFF0D6"];
 outcome [label="{{OUTCOME|prediction_id (FK)\\llabel_window_end\\llabel; label_version\\l}}"];
 publisher -> feed [label="1 : N"];
 feed -> fetch [label="1 : N"];
 feed -> article [label="1 : N"];
 article -> member [label="1 : N"];
 event -> member [label="1 : N"];
 event -> obs [label="1 : N"];
 obs -> pred [label="1 : N"];
 pred -> outcome [label="0 : 1"];
 }}''')
write('06_evaluation',f'''digraph eval {{ {HEADER} rankdir=TB;
 snapshot [label="Immutable observation snapshots\\ncutoff-time reconstructed features",fillcolor="#D8F0E6"];
 gate [label="Panel/rights gate + completeness filter\\nexclude gaps and contaminated cutoffs"];
 splits [label="Chronological folds\\ntrain -> tuning -> embargo -> sealed final"];
 runners [label="Same candidates; same cutoff; same labels\\nzero / momentum / volume / candidate"];
 metrics [label="Paired Precision@5 + calibration\\nprevalence, lead-time, blocked bootstrap"];
 audit [label="Independent audit\\nhashes | counts | provenance | model registry",fillcolor="#F1E7FA"];
 decision [label="GO / HOLD / KILL\\nwith separate data / model / utility decisions",fillcolor="#FAEECF"];
 snapshot -> gate -> splits -> runners -> metrics -> audit -> decision;
 }}''')
write('07_deployment',f'''digraph deploy {{ {HEADER} rankdir=LR;
 user [label="Editor browser\\nHTTPS + SSO/MFA",fillcolor="#D8F0E6"];
 subgraph cluster_host {{label="Single controlled cloud environment (pilot)";color="#A9C1D1";style="rounded,dashed";
 gateway [label="Reverse proxy\\nTLS termination / rate-limit",fillcolor="#E3F0F9"];
 app [label="API + Web static assets\\nnon-root container"];
 job [label="Scheduler + worker container\\nallowlisted egress"];
 db [label="Managed PostgreSQL\\nbackups + encryption",shape=cylinder,fillcolor="#F4E8D9"];
 obj [label="Object storage\\nsource-permission ACL",shape=cylinder,fillcolor="#F4E8D9"];
 mon [label="Structured logs / metrics\\nalerts + audit hashes",fillcolor="#F0E8F6"];
 }}
 sources [label="Permitted source hosts"];
 user -> gateway -> app -> db;
 sources -> job -> db;
 job -> obj;
 app -> mon [style=dashed]; job -> mon [style=dashed];
 }}''')
write('08_delivery',f'''digraph delivery {{ {HEADER} rankdir=TB;
 a [label="G0 | Source rights + 3-owner pilot\\nSTOP if unqualified",fillcolor="#FBE6E3"];
 b [label="G1 | Observability + immutable capture\\n7 consecutive days",fillcolor="#FFF0D6"];
 c [label="G2 | Event clusters + reviewer QA\\nadjudicated sample",fillcolor="#EAF3F7"];
 d [label="G3 | Frozen labels + baselines\\nprospective training window",fillcolor="#EAF3F7"];
 e [label="G4 | Sealed independent evaluation\\npaired lift + uncertainty",fillcolor="#D8F0E6"];
 f [label="G5 | Editorial usefulness evidence\\nethical limited rollout",fillcolor="#D8F0E6"];
 a -> b -> c -> d -> e -> f;
 }}''')
# hand-drawn UML sequence diagram (SVG)
w,h=1120,510
parts=[('Source RSS',120),('Collector',340),('DB / Object Store',568),('Cluster Worker',800),('Forecast Worker',1020)]
svg=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">',
'<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#56758c"/></marker></defs>',
'<rect width="1120" height="510" fill="white"/>']
for label,x in parts:
 svg.extend([f'<rect x="{x-84}" y="20" width="168" height="52" rx="8" fill="#e4f0f7" stroke="#aac5d5"/>',f'<text x="{x}" y="50" fill="#17334a" font-family="Lato" font-size="15" font-weight="700" text-anchor="middle">{label}</text>',f'<line x1="{x}" y1="72" x2="{x}" y2="482" stroke="#a9bdcb" stroke-dasharray="6,6"/>'])
def msg(y,x1,x2,text,label=''):
 svg.append(f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="#56758c" stroke-width="2" marker-end="url(#arrow)"/>')
 svg.append(f'<text x="{(x1+x2)/2}" y="{y-9}" fill="#244860" font-size="12" font-family="Lato" text-anchor="middle">{text}</text>')
msg(120,340,120,'GET /feed (allowlist)')
msg(173,120,340,'200 XML / 304 / 429')
msg(220,340,568,'append fetch receipt + first_seen')
msg(270,340,800,'eligible article IDs only')
msg(318,800,568,'write cluster_version + memberships')
msg(367,1020,568,'read frozen features at cutoff')
msg(417,1020,568,'persist prediction + run manifest')
svg.append('<rect x="42" y="446" width="1036" height="36" rx="7" fill="#f9edd5"/><text x="560" y="469" font-family="Lato" fill="#755727" font-size="13" text-anchor="middle">Failure principle: failed fetches and missing observations are never transformed into zero-interest labels.</text>')
svg.append('</svg>')
(P/'09_sequence.svg').write_text('\n'.join(svg))
print('diagrams ready')
# Re-layout the multi-step ingestion diagram into a legible 2-row snake.
W,H=1020,476
nodes=[
  (1,0,0,'Publisher RSS','allowlisted endpoint'),
  (2,1,0,'Fetch politely','ETag / bounded retries'),
  (3,2,0,'Record receipt','status + hash + first_seen'),
  (4,3,0,'Parse and gate','XML safety + source rights'),
  (5,3,1,'Normalize','canonical URL + time'),
  (6,2,1,'Deduplicate','logical article identity'),
  (7,1,1,'Persist article','provenance-linked row'),
  (8,0,1,'Create candidates','event linking queue'),
]
s=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1020 476" width="1020" height="476">','<defs><marker id="m" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#4F7A93"/></marker></defs>','<rect width="1020" height="476" fill="white"/>']
for i,col,row,t,d in nodes:
 x=24+col*252; y=25+row*211
 s.extend([f'<rect x="{x}" y="{y}" width="216" height="137" rx="12" fill="{("#E4F4EB" if i==8 else "#EAF3F8")}" stroke="#B5CBD8" stroke-width="2"/>',f'<circle cx="{x+26}" cy="{y+27}" r="16" fill="#187888"/>',f'<text x="{x+26}" y="{y+33}" fill="white" font-family="Lato" font-size="17" font-weight="bold" text-anchor="middle">{i}</text>',f'<text x="{x+18}" y="{y+76}" fill="#15384D" font-family="Lato" font-size="20" font-weight="bold">{t}</text>',f'<text x="{x+18}" y="{y+110}" fill="#4A687C" font-family="Lato" font-size="15">{d.replace("&","&amp;")}</text>'])
for c in range(3):
 for y,x1,x2 in [(93,24+c*252+216,24+(c+1)*252),(304,24+(c+1)*252,24+c*252+216)]:
  s.append(f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="#4F7A93" stroke-width="3" marker-end="url(#m)"/>')
s.append('<line x1="908" y1="162" x2="908" y2="236" stroke="#4F7A93" stroke-width="3" marker-end="url(#m)"/>')
s.append('<rect x="24" y="416" width="972" height="42" rx="7" fill="#FBECE9" stroke="#D4A69F"/><text x="510" y="443" font-family="Lato" font-size="17" font-weight="bold" text-anchor="middle" fill="#8A4C45">Any access, parser or rights failure -> quarantine; missing observations never become zero counts.</text>')
s.append('</svg>')
(P/'03_ingestion.svg').write_text('\n'.join(s))
