const speechForm=document.querySelector('#speechForm');
const speechInput=document.querySelector('#speechInput');
const speechToggle=document.querySelector('#chatToggle');

function setComposer(open) {
  speechForm.hidden=!open;
  speechToggle.setAttribute('aria-expanded',String(open));
  if(open) speechInput.focus();
  else document.querySelector('#world').focus({preventScroll:true});
}
speechToggle.addEventListener('click',()=>setComposer(speechForm.hidden));
speechForm.addEventListener('keydown',event=>{
  if(event.key==='Escape' && !event.isComposing) setComposer(false);
});
speechForm.addEventListener('submit',event=>{
  event.preventDefault();
  const message=speechInput.value.trim();
  if(!message) return;
  speechInput.value='';
  window.dispatchEvent(new CustomEvent('hodu:speech',{detail:message}));
  setComposer(false);
});
