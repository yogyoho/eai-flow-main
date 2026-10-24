import { CalendarDays, Check, ChevronDown, ChevronLeft, ChevronRight, Search } from 'lucide-react'
import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type RefObject,
} from 'react'
import { createPortal } from 'react-dom'

export interface SelectOption {
  value: string
  label: string
  disabled?: boolean
}

function useFloatingPanel<T extends HTMLElement>(
  open: boolean,
  triggerRef: RefObject<T | null>,
  panelRef: RefObject<HTMLDivElement | null>,
  onClose: () => void,
  desiredWidth: number,
  desiredHeight: number,
  matchTriggerWidth = true,
) {
  const [style, setStyle] = useState<CSSProperties>({})

  const update = useCallback(() => {
    const trigger = triggerRef.current
    if (!trigger) return
    const rect = trigger.getBoundingClientRect()
    const gap = 6
    const padding = 8
    const availableWidth = window.innerWidth - padding * 2
    const width = matchTriggerWidth
      ? Math.min(Math.max(rect.width, desiredWidth), availableWidth)
      : Math.min(desiredWidth, availableWidth)
    const spaceBelow = window.innerHeight - rect.bottom - gap - padding
    const spaceAbove = rect.top - gap - padding
    const openUp = spaceBelow < Math.min(desiredHeight, 220) && spaceAbove > spaceBelow
    const maxHeight = Math.max(120, Math.min(desiredHeight, openUp ? spaceAbove : spaceBelow))
    const left = Math.min(Math.max(padding, rect.left), window.innerWidth - width - padding)
    setStyle(
      openUp
        ? { left, bottom: window.innerHeight - rect.top + gap, width, maxHeight }
        : { left, top: rect.bottom + gap, width, maxHeight },
    )
  }, [desiredHeight, desiredWidth, matchTriggerWidth, triggerRef])

  useLayoutEffect(() => {
    if (!open) return
    update()
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
    }
  }, [open, update])

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node
      if (triggerRef.current?.contains(target) || panelRef.current?.contains(target)) return
      onClose()
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [onClose, open, panelRef, triggerRef])

  return style
}

export function Select({
  value,
  options,
  onChange,
  placeholder = '请选择',
  disabled = false,
  className = '',
  ariaLabel,
  searchable = false,
}: {
  value: string
  options: SelectOption[]
  onChange: (value: string) => void
  placeholder?: string
  disabled?: boolean
  className?: string
  ariaLabel?: string
  searchable?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(-1)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const listboxId = useId()

  const selected = options.find((option) => option.value === value)
  const filtered = query.trim()
    ? options.filter((option) => option.label.toLowerCase().includes(query.trim().toLowerCase()))
    : options

  const close = useCallback((restoreFocus = true) => {
    setOpen(false)
    setQuery('')
    setActiveIndex(-1)
    if (restoreFocus) window.requestAnimationFrame(() => triggerRef.current?.focus())
  }, [])

  const panelStyle = useFloatingPanel(open, triggerRef, panelRef, close, 200, 300)

  useEffect(() => {
    if (!open) return
    const selectedIndex = filtered.findIndex((option) => option.value === value)
    setActiveIndex(selectedIndex >= 0 ? selectedIndex : filtered.length ? 0 : -1)
    window.requestAnimationFrame(() => {
      if (searchable) searchRef.current?.focus()
      else panelRef.current?.focus()
    })
    // Reset the highlight only when opening; query changes are handled below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => {
    if (!open) return
    setActiveIndex(filtered.length ? 0 : -1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query])

  function openMenu() {
    if (disabled) return
    setOpen(true)
  }

  function choose(option: SelectOption) {
    if (option.disabled) return
    onChange(option.value)
    close()
  }

  function onTriggerKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      openMenu()
    }
  }

  function onPanelKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      event.preventDefault()
      close()
      return
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex((current) => Math.min(filtered.length - 1, Math.max(0, current + 1)))
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((current) => Math.max(0, current - 1))
      return
    }
    if (event.key === 'Home') {
      event.preventDefault()
      setActiveIndex(0)
      return
    }
    if (event.key === 'End') {
      event.preventDefault()
      setActiveIndex(filtered.length - 1)
      return
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      const option = filtered[activeIndex]
      if (option) choose(option)
    }
  }

  return (
    <div className={`select-control ${className}`}>
      <button
        ref={triggerRef}
        type="button"
        className={`select-trigger ${open ? 'is-open' : ''}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => (open ? close(false) : openMenu())}
        onKeyDown={onTriggerKeyDown}
      >
        <span className={`select-value ${selected ? '' : 'is-placeholder'}`}>{selected?.label || placeholder}</span>
        <ChevronDown size={14} className="select-chevron" />
      </button>
      {open
        ? createPortal(
            <div
              ref={panelRef}
              id={listboxId}
              className="select-menu"
              role="listbox"
              tabIndex={-1}
              style={panelStyle}
              onKeyDown={onPanelKeyDown}
            >
              {searchable ? (
                <div className="select-search">
                  <Search size={13} />
                  <input
                    ref={searchRef}
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="搜索选项"
                    aria-label="搜索选项"
                  />
                </div>
              ) : null}
              <div className="select-options">
                {filtered.length ? (
                  filtered.map((option, index) => (
                    <button
                      type="button"
                      role="option"
                      aria-selected={option.value === value}
                      className={`select-option ${index === activeIndex ? 'is-active' : ''}`}
                      disabled={option.disabled}
                      key={option.value}
                      onPointerMove={() => setActiveIndex(index)}
                      onClick={() => choose(option)}
                    >
                      <span>{option.label}</span>
                      {option.value === value ? <Check size={13} className="select-check" /> : null}
                    </button>
                  ))
                ) : (
                  <div className="select-empty">没有匹配项</div>
                )}
              </div>
            </div>,
            document.body,
          )
        : null}
    </div>
  )
}

function parseDate(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return null
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
  return Number.isNaN(date.getTime()) ? null : date
}

function dateValue(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function startOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1)
}

function addMonths(date: Date, months: number): Date {
  return new Date(date.getFullYear(), date.getMonth() + months, 1)
}

function addDays(date: Date, days: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days)
}

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']

export function DatePicker({
  value,
  onChange,
  placeholder = '选择日期',
  disabled = false,
  className = '',
  ariaLabel,
}: {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  disabled?: boolean
  className?: string
  ariaLabel?: string
}) {
  const [open, setOpen] = useState(false)
  const [viewMonth, setViewMonth] = useState(() => startOfMonth(parseDate(value) || new Date()))
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const dialogId = useId()
  const selected = parseDate(value)
  const today = dateValue(new Date())

  const close = useCallback((restoreFocus = true) => {
    setOpen(false)
    if (restoreFocus) window.requestAnimationFrame(() => triggerRef.current?.focus())
  }, [])

  const panelStyle = useFloatingPanel(open, triggerRef, panelRef, close, 272, 360, false)

  useEffect(() => {
    if (!open) return
    window.requestAnimationFrame(() => panelRef.current?.focus())
  }, [open])

  function openCalendar() {
    if (disabled) return
    setViewMonth(startOfMonth(selected || new Date()))
    setOpen(true)
  }

  function choose(date: Date) {
    onChange(dateValue(date))
    close()
  }

  function onTriggerKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === 'Enter' || event.key === ' ' || event.key === 'ArrowDown') {
      event.preventDefault()
      openCalendar()
    }
  }

  function onPanelKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      event.preventDefault()
      close()
    }
  }

  const monthStart = startOfMonth(viewMonth)
  const firstOffset = (monthStart.getDay() + 6) % 7
  const gridStart = addDays(monthStart, -firstOffset)
  const days = Array.from({ length: 42 }, (_, index) => addDays(gridStart, index))

  return (
    <div className={`date-control ${className}`}>
      <button
        ref={triggerRef}
        type="button"
        className={`date-trigger ${open ? 'is-open' : ''}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={dialogId}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => (open ? close(false) : openCalendar())}
        onKeyDown={onTriggerKeyDown}
      >
        <CalendarDays size={14} className="date-icon" />
        <span className={value ? '' : 'is-placeholder'}>{value || placeholder}</span>
      </button>
      {open
        ? createPortal(
            <div
              ref={panelRef}
              id={dialogId}
              className="date-popover"
              role="dialog"
              tabIndex={-1}
              style={panelStyle}
              onKeyDown={onPanelKeyDown}
            >
              <div className="date-head">
                <button type="button" className="date-nav" onClick={() => setViewMonth(addMonths(viewMonth, -1))} aria-label="上个月">
                  <ChevronLeft size={14} />
                </button>
                <strong>
                  {viewMonth.getFullYear()}年{viewMonth.getMonth() + 1}月
                </strong>
                <button type="button" className="date-nav" onClick={() => setViewMonth(addMonths(viewMonth, 1))} aria-label="下个月">
                  <ChevronRight size={14} />
                </button>
              </div>
              <div className="date-weekdays">
                {WEEKDAYS.map((day) => (
                  <span key={day}>{day}</span>
                ))}
              </div>
              <div className="date-grid">
                {days.map((date) => {
                  const text = dateValue(date)
                  return (
                    <button
                      type="button"
                      key={text}
                      className={`date-day ${date.getMonth() !== viewMonth.getMonth() ? 'is-outside' : ''} ${
                        text === today ? 'is-today' : ''
                      } ${text === value ? 'is-selected' : ''}`}
                      onClick={() => choose(date)}
                    >
                      {date.getDate()}
                    </button>
                  )
                })}
              </div>
              <div className="date-foot">
                <button type="button" onClick={() => choose(new Date())}>
                  今天
                </button>
                <button type="button" onClick={() => { onChange(''); close() }}>
                  清除
                </button>
              </div>
            </div>,
            document.body,
          )
        : null}
    </div>
  )
}
