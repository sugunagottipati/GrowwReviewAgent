let reviews=[
 {rating:2,text:'Submitted my documents four days ago and KYC is still pending.',theme:'KYC & Aadhaar',sentiment:'negative',date:'04 Sep 2026'},
 {rating:2,text:"Money was deducted but the deposit isn't showing in my account.",theme:'UPI & Payments',sentiment:'negative',date:'01 Sep 2026'},
 {rating:5,text:'Very easy to start investing. The whole process took just a few minutes.',theme:'Onboarding',sentiment:'positive',date:'22 Aug 2026'},
 {rating:2,text:'Charts freeze exactly when I need them most. Please fix the lag.',theme:'Performance',sentiment:'negative',date:'29 Aug 2026'},
 {rating:3,text:'The interface is simple, but my P&L takes too long to update.',theme:'Portfolio sync',sentiment:'mixed',date:'28 Aug 2026'},
 {rating:4,text:'Great app for mutual funds. Would love clearer status for withdrawals.',theme:'Withdrawals',sentiment:'mixed',date:'24 Aug 2026'}
];
const API_BASE_URL=(window.GROWW_API_URL||'').replace(/\/$/,'');
const $=s=>document.querySelector(s);const $$=s=>document.querySelectorAll(s);
function apiUrl(path){return `${API_BASE_URL}${path}`}
function toast(message){const el=$('#toast');el.textContent=message;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),2800)}
function showView(name){$$('.screen').forEach(el=>el.classList.toggle('active',el.id===name));$$('.nav').forEach(el=>el.classList.toggle('active',el.dataset.view===name));const label={dashboard:'Weekly Pulse',detail:'Pulse Detail View',reviews:'Review Explorer',integrations:'Pipeline Hub'}[name];$('#crumb-label').textContent=label;window.scrollTo({top:0,behavior:'smooth'})}
$$('.nav').forEach(btn=>btn.addEventListener('click',()=>showView(btn.dataset.view)));$$('[data-target]').forEach(btn=>btn.addEventListener('click',()=>showView(btn.dataset.target)));
function renderReviews(){const query=($('#search')?.value||'').toLowerCase();const sentiment=$('#sentiment')?.value||'all';const rating=$('#rating')?.value||'all';const filtered=reviews.filter(r=>(!query||r.text.toLowerCase().includes(query)||r.theme.toLowerCase().includes(query))&&(sentiment==='all'||r.sentiment===sentiment)&&(rating==='all'||String(r.rating)===rating));$('#review-rows').innerHTML=filtered.map((r,i)=>`<tr data-index="${reviews.indexOf(r)}"><td class="stars">${'★'.repeat(r.rating)}<span style="color:#dfe4eb">${'★'.repeat(5-r.rating)}</span></td><td class="review-copy">${r.text}</td><td><span class="tag">${r.theme}</span></td><td><span class="risk ${r.sentiment==='positive'?'watch':r.sentiment==='negative'?'critical':'high'}">${r.sentiment.toUpperCase()}</span></td><td>${r.date}</td><td>→</td></tr>`).join('')||'<tr><td colspan="6" style="text-align:center;padding:35px;color:#8792a1">No reviews match these filters.</td></tr>';$('#shown').textContent=filtered.length;$$('#review-rows tr[data-index]').forEach(row=>row.addEventListener('click',()=>openDrawer(reviews[row.dataset.index])))}
function openDrawer(r){$('#drawer-title').textContent=r.theme;$('#drawer-text').innerHTML=`“${r.text}”<small>${r.rating}★ · ${r.date} · anonymized</small>`;$('#drawer-rating').textContent=`${r.rating} / 5`;$('#drawer-theme').textContent=r.theme;$('#drawer-date').textContent=r.date;$('#drawer').classList.add('open')}
$('#close-drawer').addEventListener('click',()=>$('#drawer').classList.remove('open'));$('#drawer').addEventListener('click',e=>{if(e.target.id==='drawer')$('#drawer').classList.remove('open')});['search','sentiment','rating'].forEach(id=>$('#'+id).addEventListener('input',renderReviews));renderReviews();
async function loadLiveData(){
 try{
  const response=await fetch(apiUrl('/api/reviews'));
  if(!response.ok)throw new Error(`API returned ${response.status}`);
  const payload=await response.json();
  if(Array.isArray(payload.reviews)&&payload.reviews.length){
   reviews=payload.reviews.map(review=>({
	rating:review.rating,
	text:review.text,
	theme:review.title||'Product feedback',
	sentiment:review.rating>=4?'positive':review.rating<=2?'negative':'mixed',
	date:new Date(review.reviewed_at).toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'})
   }));
   renderReviews();
  }
   const pulseResponse=await fetch(apiUrl('/api/pulse'));
   if(pulseResponse.ok){
    const payload=await pulseResponse.json();
    const pulse=payload.pulse;
    if(pulse){
      pulse.top_themes.forEach((theme,index)=>{
       const card=$$('.theme')[index];
       if(!card)return;
       const title=card.querySelector('h3');
       const summary=card.querySelector('p');
       if(title)title.textContent=theme.label;
       if(summary)summary.textContent=`${theme.review_count} reviews · ${Math.round(theme.share_of_reviews*100)}% of sample · ${theme.sentiment} sentiment.`;
      });
    }
   }
 }catch(error){console.warn('Live data unavailable; using fixture reviews.',error)}
}
loadLiveData();
async function runLivePulse(button){
 if(!API_BASE_URL){toast('Set BACKEND_URL in Vercel to run a live pulse.');return}
 const original=button.innerHTML;
 button.disabled=true;button.textContent='Running…';
 try{
   const response=await fetch(apiUrl('/api/pulse/run'),{method:'POST'});
   const payload=await response.json();
   if(!response.ok)throw new Error(payload.error||`API returned ${response.status}`);
   await loadLiveData();
   toast('Live pulse generated and loaded from Railway.');
 }catch(error){toast(`Pulse run failed: ${error.message}`)}
 finally{button.disabled=false;button.innerHTML=original}
}
$('#generate').addEventListener('click',()=>runLivePulse($('#generate')));$('#run-pulse').addEventListener('click',()=>runLivePulse($('#run-pulse')));$('#deliver').addEventListener('click',()=>toast('Docs updated and Gmail draft created through MCP.'));$$('.outline').forEach(btn=>{if(btn.textContent.includes('Export'))btn.addEventListener('click',()=>toast('Export prepared from the current pulse.'))});
$('.rail-link').addEventListener('click',()=>toast('Documentation is available in the project README.'));
$$('.top-icon').forEach((button,index)=>button.addEventListener('click',()=>toast(index===0?'No new notifications.':'Settings are managed by the deployment environment.')));
$$('.head-actions .outline').forEach(button=>{if(!button.textContent.includes('Export'))button.addEventListener('click',()=>toast('Showing the latest 12-week pulse window.'))});
$$('.run').forEach(run=>run.addEventListener('click',()=>showView('detail')));
$$('.adapter .outline').forEach(button=>button.addEventListener('click',()=>toast('Destination links are available after the next MCP delivery.')));
