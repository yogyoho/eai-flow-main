import {
  Database,
  Download,
  FileSpreadsheet,
  Plus,
  Search,
  Upload,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { api, qs, type Json, type MasterOptions, type Paged } from '../api'
import { DatePicker, Select } from '../components/controls'
import {
  Badge,
  EmptyState,
  ErrorBanner,
  Field,
  Modal,
  Spinner,
  useToast,
} from '../components/ui'
import { dateTimeText, errorText } from '../lib/format'

const TABS = [
  { key: 'customer-groups', label: '客户集团' },
  { key: 'customers', label: '客户' },
  { key: 'mines', label: '矿井' },
  { key: 'workfaces', label: '工作面' },
  { key: 'products', label: '产品' },
  { key: 'contacts', label: '联系人' },
  { key: 'pilot-projects', label: '示范面' },
]

const COLUMNS: Record<string, Array<{ key: string; label: string; kind?: 'date' | 'bool' | 'percent' }>> = {
  'customer-groups': [
    { key: 'name', label: '集团名称' },
    { key: 'credit_code', label: '统一社会信用代码' },
    { key: 'region_code', label: '区域' },
    { key: 'is_new_customer', label: '新客户', kind: 'bool' },
  ],
  customers: [
    { key: 'name', label: '客户名称' },
    { key: 'region_code', label: '区域' },
    { key: 'address', label: '地址' },
    { key: 'related_party_status', label: '关联方' },
  ],
  mines: [
    { key: 'name', label: '矿井' },
    { key: 'region_code', label: '区域' },
    { key: 'capacity', label: '产能' },
    { key: 'gas_grade', label: '瓦斯等级' },
    { key: 'mining_height_m', label: '采高(m)' },
  ],
  workfaces: [
    { key: 'name', label: '工作面' },
    { key: 'coal_seam', label: '煤层' },
    { key: 'mining_height_m', label: '采高(m)' },
    { key: 'face_length_m', label: '面长(m)' },
  ],
  products: [
    { key: 'name', label: '产品名称' },
    { key: 'product_line', label: '产品线' },
    { key: 'model', label: '型号' },
    { key: 'is_active', label: '启用', kind: 'bool' },
  ],
  contacts: [
    { key: 'name', label: '姓名' },
    { key: 'title', label: '职务' },
    { key: 'role', label: '角色' },
    { key: 'influence', label: '影响力' },
    { key: 'stance', label: '立场' },
    { key: 'phone', label: '电话' },
  ],
  'pilot-projects': [
    { key: 'name', label: '示范面' },
    { key: 'completed_at', label: '完成时间', kind: 'date' },
    { key: 'effect', label: '效果' },
    { key: 'evidence_url', label: '证据 URL' },
  ],
}

const CREATE_FIELDS: Record<string, Array<{ key: string; label: string; type?: 'text' | 'number' | 'date' | 'select'; required?: boolean; option?: 'groups' | 'customers' | 'mines' | 'workfaces'; placeholder?: string }>> = {
  'customer-groups': [
    { key: 'name', label: '集团名称', required: true },
    { key: 'credit_code', label: '统一社会信用代码' },
    { key: 'region_code', label: '区域', placeholder: 'NORTH / NORTHWEST' },
    { key: 'is_new_customer', label: '新客户（1/0）' },
  ],
  customers: [
    { key: 'name', label: '客户名称', required: true },
    { key: 'group_id', label: '所属集团', type: 'select', option: 'groups' },
    { key: 'region_code', label: '区域', placeholder: 'NORTH / NORTHWEST' },
    { key: 'address', label: '地址' },
    { key: 'related_party_status', label: '关联方状态', placeholder: 'yes / no / unknown' },
  ],
  mines: [
    { key: 'name', label: '矿井名称', required: true },
    { key: 'customer_id', label: '所属客户', type: 'select', option: 'customers' },
    { key: 'region_code', label: '区域' },
    { key: 'capacity', label: '产能' },
    { key: 'mining_height_m', label: '采高(m)', type: 'number' },
  ],
  workfaces: [
    { key: 'name', label: '工作面名称', required: true },
    { key: 'mine_id', label: '所属矿井', type: 'select', option: 'mines' },
    { key: 'mining_height_m', label: '采高(m)', type: 'number' },
    { key: 'face_length_m', label: '面长(m)', type: 'number' },
  ],
  products: [
    { key: 'name', label: '产品名称', required: true },
    { key: 'product_line', label: '产品线', required: true },
    { key: 'model', label: '型号' },
  ],
  contacts: [
    { key: 'name', label: '姓名', required: true },
    { key: 'customer_id', label: '所属客户', type: 'select', option: 'customers' },
    { key: 'title', label: '职务' },
    { key: 'phone', label: '电话' },
  ],
  'pilot-projects': [
    { key: 'name', label: '示范面名称', required: true },
    { key: 'customer_group_id', label: '客户集团', type: 'select', option: 'groups' },
    { key: 'workface_id', label: '工作面', type: 'select', option: 'workfaces' },
    { key: 'completed_at', label: '完成日期', type: 'date' },
    { key: 'effect', label: '效果说明' },
  ],
}

export default function MasterData() {
  const { push } = useToast()
  const [tab, setTab] = useState('customers')
  const [keyword, setKeyword] = useState('')
  const [data, setData] = useState<Paged<Json> | null>(null)
  const [options, setOptions] = useState<MasterOptions | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [jobs, setJobs] = useState<Json[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await api.get<Paged<Json>>(`/master-data/${tab}${qs({ keyword, limit: 200 })}`)
      setData(result)
    } catch (err) {
      setError(errorText(err))
    } finally {
      setLoading(false)
    }
  }, [tab, keyword])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    api.get<MasterOptions>('/master-data/options').then(setOptions).catch(() => undefined)
    api.get<{ items: Json[] }>('/master-data/import-jobs').then((result) => setJobs(result.items)).catch(() => undefined)
  }, [tab])

  const columns = COLUMNS[tab] || []

  return (
    <div className="stack">
      <section className="panel snapshot-banner">
        <Database size={20} />
        <div>
          <strong>本地最小记录，明确标注来源与时间</strong>
          <p>
            QW2 不假设 ERP / CRM / MDM 可用。客户、矿井、工作面与产品是销售侧最小快照，字段完整度低于 100% 会显示并保留
            <code> source </code>与<code> data_as_of </code>。需要权威数据时请回到来源系统核对。
          </p>
        </div>
        <Badge tone="amber">快照模式</Badge>
      </section>

      <section className="panel">
        <div className="master-toolbar">
          <div className="tab-strip">
            {TABS.map((item) => (
              <button
                type="button"
                key={item.key}
                className={tab === item.key ? 'active' : ''}
                onClick={() => {
                  setTab(item.key)
                  setKeyword('')
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="filter-row compact">
            <label className="search-box">
              <Search size={16} />
              <input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="按名称过滤" />
            </label>
            <button type="button" className="button primary small" onClick={() => setCreateOpen(true)}>
              <Plus size={15} /> 新增
            </button>
            <button type="button" className="button ghost small" onClick={() => setImportOpen(true)}>
              <Upload size={15} /> 数据导入
            </button>
          </div>
        </div>

        {error ? <ErrorBanner message={error} onClose={() => setError('')} /> : null}

        {loading && !data ? (
          <Spinner />
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    {columns.map((column) => <th key={column.key}>{column.label}</th>)}
                    <th>来源</th>
                    <th>数据时点</th>
                    <th>完整度</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {data?.items.map((row) => (
                    <tr key={row.id}>
                      {columns.map((column) => (
                        <td key={column.key}>
                          {column.kind === 'bool' ? (
                            <Badge tone={row[column.key] ? 'green' : 'neutral'}>{row[column.key] ? '是' : '否'}</Badge>
                          ) : column.kind === 'percent' ? (
                            `${row[column.key] ?? '—'}%`
                          ) : column.kind === 'date' ? (
                            String(row[column.key] || '—').slice(0, 10)
                          ) : (
                            row[column.key] ?? '—'
                          )}
                        </td>
                      ))}
                      <td>
                        <Badge tone={row.source === 'seed' ? 'amber' : row.source === 'manual' ? 'teal' : 'blue'}>
                          {row.source === 'seed' ? '演示种子' : row.source === 'manual' ? '手工' : row.source}
                        </Badge>
                      </td>
                      <td>{dateTimeText(row.data_as_of)}</td>
                      <td>{row.completeness !== undefined ? `${row.completeness}%` : '—'}</td>
                      <td>{row.is_active === false ? <Badge tone="neutral">停用</Badge> : <Badge tone="green">有效</Badge>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!data?.items.length ? <EmptyState title="没有记录" description="可新增一条最小记录，或导入 CSV。" icon={<Database size={22} />} /> : null}
            <div className="pager">
              <span>共 {data?.total ?? 0} 条 · 最多显示 200 条</span>
              <span className="muted">主数据编辑会刷新 data_as_of，但不会伪装成来源系统实时同步。</span>
            </div>
          </>
        )}
      </section>

      <section className="panel">
        <div className="section-head">
          <div>
            <h3>最近导入</h3>
            <p className="muted">CSV 支持中文表头别名；校验模式回滚写入但仍记录导入结果。</p>
          </div>
          <FileSpreadsheet size={19} className="muted" />
        </div>
        <div className="mini-list">
          {jobs.slice(0, 6).map((job) => (
            <div className="mini-row" key={job.id}>
              <Badge tone={job.status === 'completed' ? 'green' : 'amber'}>{job.status}</Badge>
              <span>{job.file_name || job.type} · {job.success} 成功 / {job.failed} 失败</span>
              <small>{dateTimeText(job.created_at)}</small>
            </div>
          ))}
          {!jobs.length ? <p className="muted">还没有导入记录。</p> : null}
        </div>
      </section>

      <CreateMasterModal
        open={createOpen}
        type={tab}
        options={options}
        onClose={() => setCreateOpen(false)}
        onCreated={() => {
          setCreateOpen(false)
          push('主数据已新增', 'success')
          void load()
        }}
      />

      <ImportMasterModal
        open={importOpen}
        type={tab}
        onClose={() => setImportOpen(false)}
        onDone={() => {
          setImportOpen(false)
          push('导入任务已完成', 'success')
          void load()
          api.get<{ items: Json[] }>('/master-data/import-jobs').then((result) => setJobs(result.items)).catch(() => undefined)
        }}
      />
    </div>
  )
}

function CreateMasterModal({
  open,
  type,
  options,
  onClose,
  onCreated,
}: {
  open: boolean
  type: string
  options: MasterOptions | null
  onClose: () => void
  onCreated: () => void
}) {
  const fields = CREATE_FIELDS[type] || []
  const [values, setValues] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const optionRows = useMemo(() => {
    const map: Record<string, Array<{ id: string; name: string }>> = {
      groups: options?.groups || [],
      customers: options?.customers || [],
      mines: options?.mines || [],
      workfaces: options?.workfaces || [],
    }
    return map
  }, [options])

  async function submit() {
    setError('')
    setSaving(true)
    try {
      const payload: Json = {}
      fields.forEach((field) => {
        const value = values[field.key]
        if (value === undefined || value === '') return
        if (field.type === 'number') payload[field.key] = Number(value)
        else if (field.key === 'is_new_customer') payload[field.key] = value === '1' || value === 'true'
        else payload[field.key] = value
      })
      await api.post(`/master-data/${type}`, payload)
      setValues({})
      onCreated()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      title={`新增${TABS.find((item) => item.key === type)?.label || '主数据'}`}
      onClose={onClose}
      footer={
        <div className="modal-actions">
          <button type="button" className="button ghost" onClick={onClose}>取消</button>
          <button type="button" className="button primary" onClick={() => void submit()} disabled={saving}>
            保存
          </button>
        </div>
      }
    >
      {error ? <ErrorBanner message={error} /> : null}
      <div className="form-stack">
        {fields.map((field) => (
          <Field key={field.key} label={field.label} required={field.required}>
            {field.type === 'select' ? (
              <Select
                value={values[field.key] || ''}
                onChange={(value) => setValues((current) => ({ ...current, [field.key]: value }))}
                placeholder="请选择"
                ariaLabel={field.label}
                searchable={field.option === 'customers' || field.option === 'mines' || field.option === 'workfaces'}
                options={[
                  { value: '', label: '请选择' },
                  ...(optionRows[field.option || 'customers'] || []).map((item) => ({ value: item.id, label: item.name })),
                ]}
              />
            ) : field.type === 'date' ? (
              <DatePicker
                value={values[field.key] || ''}
                onChange={(value) => setValues((current) => ({ ...current, [field.key]: value }))}
                ariaLabel={field.label}
              />
            ) : (
              <input
                type={field.type === 'number' ? 'number' : 'text'}
                value={values[field.key] || ''}
                onChange={(event) => setValues((current) => ({ ...current, [field.key]: event.target.value }))}
                placeholder={field.placeholder}
              />
            )}
          </Field>
        ))}
        <div className="rule-note">
          <Database size={15} />
          <span>新记录会标记为 <code>source=manual</code>，并写入当前 data_as_of。</span>
        </div>
      </div>
    </Modal>
  )
}

function ImportMasterModal({
  open,
  type,
  onClose,
  onDone,
}: {
  open: boolean
  type: string
  onClose: () => void
  onDone: () => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [dryRun, setDryRun] = useState(false)
  const [result, setResult] = useState<Json | null>(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [dragging, setDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) return
    setFile(null)
    setDryRun(false)
    setResult(null)
    setError('')
    setDragging(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }, [open])

  function chooseFile(next: File | null) {
    setResult(null)
    setError('')
    if (!next) {
      setFile(null)
      return
    }
    if (/\.xls$/i.test(next.name)) {
      setFile(null)
      setError('旧版 .xls 暂不支持，请另存为 .xlsx 后上传')
      return
    }
    if (!/\.(csv|xlsx|xlsm)$/i.test(next.name)) {
      setFile(null)
      setError('仅支持 .csv、.xlsx 或 .xlsm 文件')
      return
    }
    if (next.size > 10 * 1024 * 1024) {
      setFile(null)
      setError('文件不能超过 10MB')
      return
    }
    setFile(next)
  }

  function fileSize(bytes: number) {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  }

  async function submit() {
    if (!file) return
    setError('')
    setSaving(true)
    try {
      const form = new FormData()
      form.set('data_type', type)
      form.set('file', file)
      form.set('dry_run', String(dryRun))
      const response = await api.upload<Json>('/master-data/import/upload', form)
      setResult(response)
      if (!dryRun) onDone()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      title={`数据导入 · ${TABS.find((item) => item.key === type)?.label || type}`}
      onClose={onClose}
      footer={
        <div className="modal-actions">
          <button type="button" className="button ghost" onClick={onClose}>关闭</button>
          <button type="button" className="button primary" onClick={() => void submit()} disabled={!file || saving}>
            {saving ? '导入中…' : dryRun ? '校验' : '导入'}
          </button>
        </div>
      }
    >
      {error ? <ErrorBanner message={error} /> : null}
      <div className="form-stack">
        <div className="rule-note">
          <FileSpreadsheet size={15} />
          <span>支持 Excel (.xlsx/.xlsm) 与 CSV，首行为表头。CSV 可为 UTF-8 BOM 或 GBK；支持中文别名，例如“客户名称”“工作面名称”。</span>
        </div>
        <div className="field">
          <span className="field-label">
            数据文件<em>*</em>
          </span>
          <input
            ref={fileInputRef}
            type="file"
            className="upload-input"
            accept=".csv,.xlsx,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            onChange={(event) => {
              chooseFile(event.target.files?.[0] || null)
              event.target.value = ''
            }}
          />
          <div
            className={`upload-dropzone ${dragging ? 'is-dragging' : ''} ${file ? 'has-file' : ''}`}
            role="button"
            tabIndex={0}
            aria-label="选择或拖拽数据文件"
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                fileInputRef.current?.click()
              }
            }}
            onDragOver={(event) => {
              event.preventDefault()
              event.dataTransfer.dropEffect = 'copy'
              setDragging(true)
            }}
            onDragLeave={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false)
            }}
            onDrop={(event) => {
              event.preventDefault()
              setDragging(false)
              chooseFile(event.dataTransfer.files?.[0] || null)
            }}
          >
            <span className="upload-dropzone-icon">
              <Upload size={20} />
            </span>
            <div className="upload-dropzone-copy">
              <strong>{file ? file.name : '拖拽文件到此处，或点击选择'}</strong>
              <span>{file ? `${fileSize(file.size)} · 点击更换文件` : 'Excel (.xlsx/.xlsm) 或 CSV，最大 10MB'}</span>
            </div>
          </div>
          {file ? (
            <button
              type="button"
              className="text-link upload-remove"
              onClick={() => {
                chooseFile(null)
                if (fileInputRef.current) fileInputRef.current.value = ''
              }}
            >
              移除已选文件
            </button>
          ) : null}
        </div>
        <label className="check-line">
          <input type="checkbox" checked={dryRun} onChange={(event) => setDryRun(event.target.checked)} />
          <span>仅校验，不写入（仍记录导入任务）</span>
        </label>
        {result ? (
          <div className="import-result">
            <strong>{result.dry_run ? '校验完成' : '导入完成'}</strong>
            <span>共 {result.total} 行 · 成功 {result.success} · 失败 {result.failed}</span>
            {result.errors?.length ? (
              <div className="mini-list">
                {result.errors.slice(0, 8).map((item: Json, index: number) => (
                  <div className="mini-row" key={index}>
                    <Badge tone="red">第 {item.row} 行</Badge>
                    <span>{item.error}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
        <button
          type="button"
          className="text-link"
          onClick={() => {
            const sample = type === 'customers' ? '客户名称,区域,地址\n示例客户,NORTH,示例地址\n' : '名称\n示例记录\n'
            const blob = new Blob([`\uFEFF${sample}`], { type: 'text/csv;charset=utf-8' })
            const url = URL.createObjectURL(blob)
            const anchor = document.createElement('a')
            anchor.href = url
            anchor.download = `${type}-template.csv`
            anchor.click()
            URL.revokeObjectURL(url)
          }}
        >
          <Download size={14} /> 下载 CSV 模板
        </button>
      </div>
    </Modal>
  )
}
