import type { Job, PageKey } from '../api'

const statusLabels:Record<string,string>={queued:'排队中',running:'执行中',completed:'已完成',partial:'部分完成',failed:'失败',paused:'已暂停',cancelled:'已取消',interrupted:'已中断',cancelling:'正在取消',stalled:'可能停滞'}
const stageLabels:Record<string,string>={queued:'等待执行',running:'正在执行',provider_preflight:'检查研究连接',source_request:'检索权威信息源',source_gate:'审查信息源门槛',value_chain_request:'梳理产业链',value_chain_gate:'审查产业链门槛',entity_request:'检索实体与研究组',entity_gate:'审查实体覆盖门槛',persisting:'保存研究结果',quality_gate:'成品质量检查',sources:'整理信息源',scenario:'构建产业情景',agenda:'生成研究议程',completed:'任务完成'}
const operationLabels:Record<string,string>={daily:'每日情报',weekly:'周报',monthly:'月报',quarterly:'季报',bootstrap:'行业初始化',coverage:'覆盖搜索',history:'历史证据',report:'行业报告',deep_report:'深度研究',impact:'影响分析',lab:'Intelligence Lab'}
const errorLabels:Record<string,string>={authentication:'登录状态异常',configuration:'连接配置错误',invalid_model:'模型不可用',unsupported_tool:'缺少所需工具',permission:'权限不足',quota:'额度不足',artifact_quality:'成品质量未通过',process_failure:'任务执行失败',partial:'部分来源未完成',cancel_requested:'用户已取消',legacy_process:'旧任务执行失败'}

const hasHan=(value:string)=>/[\u3400-\u9fff]/.test(value)

export const jobStatusLabel=(status:string)=>statusLabels[status]||'状态未知'
export const jobStageLabel=(stage?:string|null,operation?:string|null)=>{
  const value=String(stage||'').trim()
  if(!value)return '等待阶段信息'
  if(stageLabels[value])return stageLabels[value]
  if(hasHan(value))return value
  return `${operationLabels[String(operation||'')]||'任务'}处理中`
}
export const jobErrorLabel=(category?:string|null)=>errorLabels[String(category||'')]||''
export const isTerminalJob=(job:Job)=>['completed','partial','failed','paused','cancelled','interrupted'].includes(job.status)

export function jobDestination(job:Job):{page:PageKey;href:string;label:string}|null {
  const mapping:Record<string,[PageKey,string]>={
    daily:['daily','查看每日情报'],bootstrap:['overview','查看行业概览'],
    coverage:['research','查看覆盖结果'],history:['research','查看历史覆盖'],
    weekly:['products','查看研究产物'],monthly:['products','查看研究产物'],
    quarterly:['products','查看研究产物'],report:['products','查看研究产物'],
    deep_report:['products','查看研究产物'],impact:['products','查看研究产物'],
    lab:['research','查看研究助手'],
  }
  const target=mapping[String(job.operation||'')]
  return target?{page:target[0],href:`#/${target[0]}`,label:target[1]}:null
}
