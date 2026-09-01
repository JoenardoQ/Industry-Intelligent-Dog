import { Download, ExternalLink, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { apiText, artifactUrl, type ProductItem } from '../../api'
import { ChainGraph, Empty, Loading } from '../shared'

const slug=(value:string)=>value.trim().toLocaleLowerCase().replace(/[^\p{L}\p{N}]+/gu,'-').replace(/^-|-$/g,'')
const safeUrl=(value:string)=>defaultUrlTransform(value)
const referenceParts=(item:unknown)=>{
  if(typeof item==='string')return {label:item,url:item}
  if(item&&typeof item==='object'){
    const record=item as Record<string,unknown>
    const url=String(record.url||record.href||'')
    return {label:String(record.title||record.name||url||JSON.stringify(item)),url}
  }
  return {label:String(item??''),url:''}
}

export default function ArtifactReader({artifact}:{artifact:ProductItem|null}) {
  const path=artifact?.report_file||artifact?.path||artifact?._file||undefined
  const [text,setText]=useState('');const [loading,setLoading]=useState(false);const [error,setError]=useState('');const [query,setQuery]=useState('')
  useEffect(()=>{setError('');setText(artifact?.summary||'');if(!path)return;setLoading(true);apiText(`/artifact?path=${encodeURIComponent(path)}`).then(setText).catch(reason=>setError(String(reason))).finally(()=>setLoading(false))},[path,artifact?.summary])
  const headings=useMemo(()=>[...text.matchAll(/^(#{1,3})\s+(.+)$/gm)].map(match=>({level:match[1].length,title:match[2].trim(),id:slug(match[2])})),[text])
  const matches=query.trim()?text.toLocaleLowerCase().split(query.trim().toLocaleLowerCase()).length-1:0
  if(!artifact)return <Empty title="暂无研究产物" body="使用周期或研究按钮生成第一份产物。" compact/>
  if(loading)return <Loading label="正在安全载入产物…"/>
  const graph=artifact.visualization?.directed_graph
  const graphNodes=graph?.nodes??[];const graphEdges=graph?.edges??[]
  const limitations=artifact.limitations??[];const references=artifact.references??[]
  const quality=artifact.quality as {passed?:boolean;failures?:{code?:string}[]}|undefined
  return <div className="artifact-reader"><header className="reader-meta"><div><span className="eyebrow">{artifact.status||'unknown'}</span><h2>{artifact.title||artifact.name||artifact._key||'未命名产物'}</h2><p>{artifact.generated_at||artifact.window_end||'生成时间未知'} · {artifact.provider||'Provider 未记录'}{artifact.model?` / ${artifact.model}`:''}</p></div><div className="section-actions">{artifact.portable_file&&<a className="button primary" href={artifactUrl(artifact.portable_file)} download target="_blank" rel="noreferrer"><Download/>离线单文件</a>}{path&&<a className="button secondary" href={artifactUrl(path)} target="_blank" rel="noreferrer">打开原文 <ExternalLink/></a>}</div></header>
    {(artifact.status==='partial'||error||limitations.length>0)&&<div className="artifact-warning" role="status"><strong>{error?'读取失败':artifact.status==='partial'?'产物部分完成':'已声明限制'}</strong><p>{error||limitations.map(item=>typeof item==='string'?item:JSON.stringify(item)).join('；')||'部分数据或证据未达到生成门槛。'}</p></div>}
    {quality?.passed===false&&<div className="artifact-warning" role="status"><strong>成品质量门未通过</strong><p>{(quality.failures||[]).map(item=>item.code).filter(Boolean).join(' · ')}</p></div>}
    <div className="artifact-tools"><label className="search-field"><span className="sr-only">在产物内搜索</span><Search/><input value={query} onChange={event=>setQuery(event.target.value)} placeholder="在产物内搜索"/></label><span>{query?`${matches} 处匹配`:`${headings.length} 个章节`}</span></div>
    {headings.length>0&&<nav className="artifact-toc" aria-label="文档目录">{headings.map((heading,index)=><a key={`${heading.id}:${index}`} href={`#${heading.id}`} style={{paddingInlineStart:`${(heading.level-1)*14}px`}}>{heading.title}</a>)}</nav>}
    {graphNodes.length?<div className="embedded-chain"><span className="eyebrow">DIRECTED VALUE CHAIN</span><ChainGraph nodes={graphNodes.map(node=>({...node,name:node.label||node.name}))} edges={graphEdges}/></div>:null}
    <article className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml urlTransform={safeUrl} components={{h1:({children})=><h1 id={slug(String(children))}>{children}</h1>,h2:({children})=><h2 id={slug(String(children))}>{children}</h2>,h3:({children})=><h3 id={slug(String(children))}>{children}</h3>,a:({href,children})=><a href={href} target={href?.startsWith('http')?'_blank':undefined} rel={href?.startsWith('http')?'noreferrer':undefined}>{children}</a>}}>{text||'该产物没有可读正文。'}</ReactMarkdown></article>
    {references.length>0&&<section className="artifact-references"><h2>引用</h2><ol>{references.map((item,index)=>{const {label,url}=referenceParts(item);const href=safeUrl(url);return <li key={index}>{href?<a href={href} target="_blank" rel="noreferrer">{label}</a>:label}</li>})}</ol></section>}
  </div>
}
