/* scenarios-engine.js — Vantage Scenarios Global War Gaming
   Renders from /scenarios.json — Auto-bootstraps */

var _scnData = null;

function scnEsc(s){return(s||'').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function scnFmt(s){return(s||'').replace(/\n/g,'<br>').replace(/\\n/g,'<br>');}
function scnProbClass(p){return p>=65?'high':p>=35?'med':'low';}
function scnDomainClass(d){
  var m={'military':'mil','economic':'econ','political':'pol','humanitarian':'hum',
    'cyber':'cyber','corporate':'corp','criminal':'crime','information':'info',
    'alliance':'alliance','energy':'energy','financial':'finance'};
  return m[(d||'').toLowerCase()]||'econ';
}

function scnRenderDomains(domains){
  if(!domains||domains.length===0)return '';
  var h='<div class="s-domains">';
  domains.forEach(function(d){
    var cls=scnDomainClass(d.domain);
    h+='<div class="s-domain '+cls+'"><div class="s-domain-label '+cls+'">'+scnEsc(d.domain)+'</div>';
    h+='<div class="s-domain-text">'+scnFmt(d.impact)+'</div></div>';
  });
  return h+'</div>';
}

function scnRenderBranch(b,idx){
  var probCls=scnProbClass(b.probability||0);
  var h='<div class="s-branch" onclick="scnToggleBranch(this,event)">';
  h+='<div class="s-branch-header"><span class="s-branch-name">'+scnEsc(b.name||'Path '+(idx+1))+'</span>';
  h+='<span class="s-branch-prob '+probCls+'">'+(b.probability||'?')+'%</span></div>';
  h+='<div class="s-branch-body">';
  if(b.description) h+='<div class="s-branch-desc">'+scnFmt(b.description)+'</div>';
  if(b.timeline) h+='<div class="s-branch-desc"><b style="color:var(--text-faint);font-size:0.56rem;letter-spacing:0.06em;text-transform:uppercase">Timeline:</b> '+scnFmt(b.timeline)+'</div>';
  h+=scnRenderDomains(b.domains);
  h+='</div></div>';
  return h;
}

function scnRenderCard(s){
  var threat=(s.threat_level||'monitoring').toLowerCase();
  var trigProb=s.trigger_probability||0;
  var h='<div class="s-card '+threat+'" data-cat="'+scnEsc(s.category||'')+'" data-region="'+scnEsc(s.region||'')+'" data-threat="'+threat+'" onclick="scnToggle(this,event)">';
  
  // Top
  h+='<div class="s-top"><div class="s-threat">';
  h+='<div class="s-threat-level '+threat+'">'+scnEsc(threat)+'</div>';
  h+='<div class="s-trigger-prob '+scnProbClass(trigProb)+'">'+trigProb+'%</div>';
  h+='<div class="s-prob-label">Trigger</div>';
  h+='</div><div class="s-info">';
  h+='<div class="s-title">'+scnFmt(s.title||'')+'</div>';
  if(s.trigger_condition) h+='<div class="s-trigger-line"><b>Trigger: </b>'+scnFmt(s.trigger_condition)+'</div>';
  h+='<div class="s-meta-row">';
  if(s.categories){(Array.isArray(s.categories)?s.categories:[s.categories]).forEach(function(c){
    h+='<span class="s-tag '+(c||'').toLowerCase()+'">'+scnEsc(c)+'</span>';
  });}else if(s.category){h+='<span class="s-tag '+(s.category||'').toLowerCase()+'">'+scnEsc(s.category)+'</span>';}
  if(s.regions){(Array.isArray(s.regions)?s.regions:[s.regions]).forEach(function(r){
    h+='<span class="s-tag region">'+scnEsc(r)+'</span>';
  });}else if(s.region){h+='<span class="s-tag region">'+scnEsc(s.region)+'</span>';}
  if(s.timeline) h+='<span style="font-size:0.58rem;color:var(--text-faint)">'+scnEsc(s.timeline)+'</span>';
  h+='</div></div><div class="s-expand-icon">▸</div></div>';

  // Body
  h+='<div class="s-body">';

  // Players
  if(s.players&&s.players.length>0){
    h+='<div class="s-section-label">Players</div><div class="s-players">';
    s.players.forEach(function(p){
      h+='<div class="s-player"><div class="s-player-name">'+scnEsc(p.name)+'</div>';
      if(p.objective) h+='<div class="s-player-detail"><b>Objective</b>'+scnFmt(p.objective)+'</div>';
      if(p.capability) h+='<div class="s-player-detail"><b>Capability</b>'+scnFmt(p.capability)+'</div>';
      if(p.constraint) h+='<div class="s-player-detail"><b>Constraint</b>'+scnFmt(p.constraint)+'</div>';
      h+='</div>';
    });
    h+='</div>';
  }

  // Perspectives (Red/Blue/Gray)
  if(s.red_team||s.blue_team||s.gray_actors){
    h+='<div class="s-section-label">Perspectives</div><div class="s-perspectives">';
    if(s.red_team){
      h+='<div class="s-persp red"><div class="s-persp-title red">Red Team — Adversary</div>';
      h+='<div class="s-persp-text">'+scnFmt(s.red_team)+'</div></div>';
    }
    if(s.blue_team){
      h+='<div class="s-persp blue"><div class="s-persp-title blue">Blue Team — US/Allies</div>';
      h+='<div class="s-persp-text">'+scnFmt(s.blue_team)+'</div></div>';
    }
    if(s.gray_actors){
      h+='<div class="s-persp gray"><div class="s-persp-title gray">Gray — Opportunists</div>';
      h+='<div class="s-persp-text">'+scnFmt(s.gray_actors)+'</div></div>';
    }
    h+='</div>';
  }

  // Branch paths
  if(s.branches&&s.branches.length>0){
    h+='<div class="s-section-label">Branch Paths — Possible Futures</div><div class="s-branches">';
    s.branches.forEach(function(b,i){h+=scnRenderBranch(b,i);});
    h+='</div>';
  }

  // Historical analog
  if(s.historical_analog){
    h+='<div class="s-section-label">Historical Analog</div>';
    h+='<div class="s-block analog"><div class="s-block-label analog">Precedent</div>';
    h+='<div class="s-block-text">'+scnFmt(s.historical_analog)+'</div></div>';
  }

  // Early warning indicators
  if(s.early_warning&&s.early_warning.length>0){
    h+='<div class="s-section-label">Early Warning Indicators</div>';
    h+='<div class="s-block indicators"><div class="s-block-label indicators">Watch For</div>';
    s.early_warning.forEach(function(ind){
      if(typeof ind==='string'){
        h+='<div class="s-ind-item"><span class="s-ind-icon">◉</span><span class="s-ind-text">'+scnFmt(ind)+'</span></div>';
      }else{
        var statusCls=(ind.status||'watching').toLowerCase();
        h+='<div class="s-ind-item"><span class="s-ind-icon">◉</span><span class="s-ind-text">'+scnFmt(ind.text||ind.signal||'')+'</span>';
        if(ind.status) h+='<span class="s-ind-status '+statusCls+'">'+scnEsc(ind.status.toUpperCase())+'</span>';
        h+='</div>';
      }
    });
    h+='</div>';
  }

  // Connected scenarios/predictions
  if(s.connected){
    h+='<div class="s-section-label">Connected Scenarios & Predictions</div>';
    h+='<div class="s-block connected"><div class="s-block-label connected">Cascade Effects</div>';
    h+='<div class="s-block-text">'+scnFmt(s.connected)+'</div></div>';
  }

  if(s.sources) h+='<div class="s-src">'+scnEsc(s.sources)+'</div>';
  h+='</div></div>';
  return h;
}

function scnRender(){
  var container=document.getElementById('view-scenarios');
  if(!container||!_scnData)return;

  var h='<div class="scn-head"><h2>Scenarios <span>— Global War Gaming</span></h2>';
  h+='<div class="scn-sub">Full-spectrum simulations across military, economic, political, technology, criminal, and information domains</div>';
  h+='<div class="scn-ts">Generated '+scnEsc(_scnData.generated_at||'')+' · Driven by current intelligence</div></div>';

  // Stats
  var st=_scnData.stats||{};
  h+='<div class="scn-stats">';
  h+='<div class="scn-stat"><div class="scn-stat-num" style="color:#e05555">'+(st.critical||0)+'</div><div class="scn-stat-label">Critical</div></div>';
  h+='<div class="scn-stat"><div class="scn-stat-num" style="color:#d4a84b">'+(st.elevated||0)+'</div><div class="scn-stat-label">Elevated</div></div>';
  h+='<div class="scn-stat"><div class="scn-stat-num" style="color:#5b8def">'+(st.monitoring||0)+'</div><div class="scn-stat-label">Monitoring</div></div>';
  h+='<div class="scn-stat"><div class="scn-stat-num" style="color:var(--text-faint)">'+(st.dormant||0)+'</div><div class="scn-stat-label">Dormant</div></div>';
  h+='<div class="scn-stat"><div class="scn-stat-num" style="color:#4ec9b0">'+(st.total_branches||0)+'</div><div class="scn-stat-label">Branch Paths</div></div>';
  h+='</div>';

  // Filters
  h+='<div class="scn-filters"><span class="scn-flabel">Threat:</span>';
  h+='<button class="scn-chip active" onclick="scnFilter(\'all\',this)">All</button>';
  h+='<button class="scn-chip" onclick="scnFilter(\'critical\',this)">Critical</button>';
  h+='<button class="scn-chip" onclick="scnFilter(\'elevated\',this)">Elevated</button>';
  h+='<div class="scn-divider"></div><span class="scn-flabel">Domain:</span>';
  var cats=['Military','Economic','Political','Technology','Criminal','Climate','Information','Black Swan'];
  cats.forEach(function(c){h+='<button class="scn-chip" onclick="scnFilter(\''+c.toLowerCase().replace(' ','')+'\',this)">'+c+'</button>';});
  h+='</div>';

  // Render scenarios
  (_scnData.scenarios||[]).forEach(function(s){h+=scnRenderCard(s);});

  container.innerHTML=h;
}

function scnToggle(card,e){
  if(e.target.closest('.s-body')||e.target.closest('.s-branch'))return;
  card.classList.toggle('open');
}
function scnToggleBranch(branch,e){
  e.stopPropagation();
  if(e.target.closest('.s-branch-body'))return;
  branch.classList.toggle('open');
}
function scnFilter(cat,btn){
  var container=document.getElementById('view-scenarios');
  container.querySelectorAll('.scn-chip').forEach(function(c){c.classList.remove('active');});
  btn.classList.add('active');
  var cards=container.querySelectorAll('.s-card');
  if(cat==='all'){cards.forEach(function(c){c.style.display='';});return;}
  cards.forEach(function(c){
    var threat=c.getAttribute('data-threat')||'';
    var cardCat=(c.getAttribute('data-cat')||'').toLowerCase();
    var match=(threat===cat)||(cardCat.indexOf(cat)>-1);
    c.style.display=match?'':'none';
  });
}

// Bootstrap
(function(){
  var link=document.createElement('link');
  link.rel='stylesheet';link.href='/scenarios-engine.css';
  document.head.appendChild(link);
  fetch('/scenarios.json').then(function(r){
    if(!r.ok)return null;return r.json();
  }).then(function(data){
    if(data&&data.scenarios){_scnData=data;scnRender();}
  }).catch(function(e){console.log('Scenarios: no data yet');});
})();
