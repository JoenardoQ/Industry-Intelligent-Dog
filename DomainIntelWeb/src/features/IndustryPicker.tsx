import { useEffect, useId, useRef, useState } from 'react'
import { Building2, Check, ChevronDown } from 'lucide-react'
import type { Industry } from '../api'

export default function IndustryPicker({industries,value,onChange,disabled=false}:{industries:Industry[];value:string;onChange:(folder:string)=>void;disabled?:boolean}){
  const [open,setOpen]=useState(false)
  const current=Math.max(0,industries.findIndex(item=>item.folder===value))
  const [active,setActive]=useState(current)
  const root=useRef<HTMLDivElement>(null)
  const listId=useId()
  const selected=industries[current]
  useEffect(()=>setActive(current),[current])
  useEffect(()=>{const close=(event:PointerEvent)=>{if(!root.current?.contains(event.target as Node))setOpen(false)};addEventListener('pointerdown',close);return()=>removeEventListener('pointerdown',close)},[])
  const choose=(index:number)=>{const item=industries[index];if(item){onChange(item.folder);setOpen(false)}}
  const keyboard=(event:React.KeyboardEvent<HTMLButtonElement>)=>{
    if(event.key==='ArrowDown'||event.key==='ArrowUp'){
      event.preventDefault()
      if(!open){setOpen(true);setActive(current);return}
      const delta=event.key==='ArrowDown'?1:-1
      setActive(index=>(index+delta+industries.length)%industries.length)
    }else if(event.key==='Enter'||event.key===' '){event.preventDefault();if(open)choose(active);else setOpen(true)}
    else if(event.key==='Escape'){setOpen(false)}
  }
  return <div className="industry-picker" ref={root}><Building2/><button type="button" role="combobox" aria-label="当前行业" aria-expanded={open} aria-controls={listId} aria-activedescendant={open?`${listId}-${active}`:undefined} disabled={disabled||!industries.length} onClick={()=>setOpen(value=>!value)} onKeyDown={keyboard}><span><small>当前行业</small><strong>{selected?.name||'选择行业'}</strong></span><ChevronDown/></button>{open&&<div className="industry-picker-menu" id={listId} role="listbox" aria-label="行业列表">{industries.map((item,index)=><button id={`${listId}-${index}`} type="button" role="option" aria-selected={item.folder===value} className={index===active?'active':''} key={item.folder} onMouseEnter={()=>setActive(index)} onClick={()=>choose(index)}><span><strong>{item.name}</strong><small>{item.folder}</small></span>{item.folder===value&&<Check/>}</button>)}</div>}</div>
}
