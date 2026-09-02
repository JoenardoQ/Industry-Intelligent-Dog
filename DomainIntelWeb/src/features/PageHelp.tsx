import { useEffect, useRef, useState } from 'react'
import { HelpCircle, X } from 'lucide-react'
import type { PageKey } from '../api'

type Guide={title:string;intro:string;steps:string[];features:string[];notes:string[]}

const guides:Record<PageKey,Guide>={
  overview:{title:'行业概览',intro:'这里是一个行业的研究入口：先看知识覆盖，再沿产业链进入来源、实体和研究产物。数字卡片都应能打开对应明细，而不是只做展示。',steps:['先检查信息源、文档、实体和已核验事实的数量，识别空白。','沿有向产业链从上游看到下游；选择节点查看关联企业、机构与证据。','使用页面快捷入口补充来源或启动初始化研究。'],features:['知识结构与产业链总览','覆盖统计与可点击明细','最新资料时间和研究入口'],notes:['“候选”不等于已核验事实。','数量多不代表覆盖全面，应同时观察产业链节点、地域和来源类型。']},
  daily:{title:'每日情报',intro:'每日情报默认覆盖前一日凌晨 04:00 到当前系统时间，聚合同一事件并保留来源与审核状态，适合快速判断今天真正发生了什么。',steps:['先按标题浏览去重后的事件，再按类别或来源排序。','打开条目核对摘要、日期、发布者和原始证据链接。','多选后可批量管理；重要主题可继续交给研究 Agent 分析。'],features:['标题、类别与来源排序','新闻网站、开发者、论文作者和自媒体的可读来源名','首次出现、持续升温与七日趋势','多选、全选和一键删除'],notes:['没有足够历史时，“漂移”应显示为没有变化。','社交媒体和自媒体默认是线索，不能单独支撑高风险事实。']},
  knowledge:{title:'实体与关系',intro:'这里保存行业中的企业、研究机构、人物、产品、技术与它们之间的关系。它用于建立认知地图，不是简单的公司名单。',steps:['用搜索和筛选定位实体。','打开实体查看别名、产业链位置、关系和关联证据。','优先处理候选实体与缺少证据的关系。'],features:['实体检索与分类','上下游角色和关系网络','候选、已接受等审核状态'],notes:['同名实体可能属于不同国家或类别。','关系方向、有效期和证据必须同时核对。']},
  products:{title:'研究产物',intro:'这里生成和阅读周、月、季及更长周期的情报汇总与行业报告。报告把已经收集的证据组织为可阅读结论，并不替代事实核验。',steps:['选择周期或报告类型；默认参数来自当前文档和全局任务设置。','一键生成后到任务中心查看真实进度。','完成后阅读正文、图表和证据链接，并检查 partial 或质量警告。'],features:['周、月、季、半年、两年和五年产物','Markdown 报告与单文件 HTML 导出','产业链有向图和其他可视化'],notes:['长周期任务会将采样均匀分布到整个时间范围。','格式完整不代表研究成功；质量门失败的产物会标为 partial。']},
  sources:{title:'信息源',intro:'信息源页面分开管理完整的来源目录与实际监控的动态活跃池。目录可以跨行业复用；活跃池只保留能增加权威性、地域、主题或发布者覆盖的来源。',steps:['先看各类别覆盖和来源健康状态。','启动来源检索，审查候选的发布者身份、代表性和可访问性。','按行业接受、拒绝或手动添加来源；不要仅因抓取困难就删除优质来源。'],features:['官方、协会、论文、公司披露、媒体、社区与自媒体等类别','每类权威代表来源与候选审查','共享目录、行业归属和动态活跃池'],notes:['链接可访问不等于内容支持结论。','爬取不到的优质来源仍可保留为推荐或人工阅读来源。']},
  research:{title:'研究助手',intro:'研究助手用于把问题拆成可验证的主张、证据和研究议程，也可以通过右侧 Agent 对话提出分析请求。它面向知识边界拓展，而不是预设用户只能问固定问题。',steps:['输入研究目标或从覆盖缺口选择议题。','检查 Agent 返回的引用、证据定位和冲突。','只有在执行卡片上确认后，IntDog 才会生成报告或启动任务。'],features:['研究议程与覆盖缺口','Agent 结果导入及逐条审核','语义支持、数值一致性和独立佐证门槛'],notes:['Agent 的自然语言回答不会直接写入正式事实。','观点、预测和事实使用不同的证据门槛。']},
  jobs:{title:'任务中心',intro:'任务中心展示采集、分析和报告生成的权威运行状态。这里的阶段、进度、日志和结果来自任务账本，而不是前端计时动画。',steps:['查看运行中任务的阶段、耗时和代表性日志。','失败或部分完成时打开错误原因，再决定重试。','完成后通过结果链接返回每日情报、知识库或研究产物。'],features:['排队、运行、暂停、部分完成与失败状态','取消、重试和中断恢复','Provider、时间窗口与结果类型'],notes:['一秒完成只应出现在真正无需执行的操作。','关闭窗口后的后台任务仍受授权和凭据生命周期约束。']},
  system:{title:'系统状态',intro:'这里管理行业、Agent/API 连接、全局任务默认值、自动化、数据与回收站。多数用户只需完成一次连接设置，之后按行业使用默认配置。',steps:['先确认运行环境和本地数据库正常。','检测或手动选择 Agent CLI；也可配置 API、MCP 或任务包。','设置全局默认；只有显式创建的行业覆盖项不会被全局修改替换。','在行业管理中创建、重命名、导入、导出或归档行业。'],features:['同环境 Agent 自动检测和手动路径选择','原生会话、CLI、API、MCP 与任务包连接层级','本机数据、自动化授权和可恢复回收站'],notes:['IntDog 不会连接或劫持一个已经打开的 Agent GUI。','“已检测”不等于“已登录且协议可用”；以诊断结果为准。']},
}

export default function PageHelp({page}:{page:PageKey}){
  const [open,setOpen]=useState(false)
  const trigger=useRef<HTMLButtonElement>(null)
  const guide=guides[page]
  const close=()=>{setOpen(false);queueMicrotask(()=>trigger.current?.focus())}
  useEffect(()=>{if(!open)return;const onKey=(event:KeyboardEvent)=>{if(event.key==='Escape')close()};addEventListener('keydown',onKey);return()=>removeEventListener('keydown',onKey)},[open])
  return <>
    <button ref={trigger} className="page-help-button" aria-label="打开本页使用指南" onClick={()=>setOpen(true)}><HelpCircle/></button>
    {open&&<div className="page-help-overlay" onMouseDown={event=>{if(event.target===event.currentTarget)close()}}><section className="page-help-dialog" role="dialog" aria-modal="true" aria-label={`${guide.title}使用指南`}><header><div><span>PAGE GUIDE</span><h2>{guide.title}使用指南</h2></div><button className="icon-button" aria-label="关闭使用指南" onClick={close}><X/></button></header><p className="page-help-intro">{guide.intro}</p><div className="page-help-section"><h3>推荐使用顺序</h3><ol>{guide.steps.map(item=><li key={item}>{item}</li>)}</ol></div><div className="page-help-section"><h3>本页能做什么</h3><ul>{guide.features.map(item=><li key={item}>{item}</li>)}</ul></div><div className="page-help-section page-help-notes"><h3>需要留意</h3><ul>{guide.notes.map(item=><li key={item}>{item}</li>)}</ul></div></section></div>}
  </>
}
