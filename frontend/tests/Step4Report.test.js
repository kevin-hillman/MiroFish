import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import Step4Report from '../src/components/Step4Report.vue'
import { getAgentLog, getConsoleLog, getReport } from '../src/api/report'

vi.mock('../src/api/report', () => ({
  getReport: vi.fn(),
  getAgentLog: vi.fn(),
  getConsoleLog: vi.fn()
}))

const savedReport = (overrides = {}) => ({
  report_id: 'report_saved',
  simulation_id: 'sim_saved',
  status: 'completed',
  error: null,
  outline: {
    title: 'Buybacklinks-Auswertung',
    summary: 'Auswertung der Originalaktionen, keine Marktforschung.',
    sections: [
      { title: 'Beobachtungen', content: '**Herkunft:** Codex-Auswertung, kein nativer ReportAgent-Lauf.' },
      { title: 'Kaufblocker', content: 'Aktuelle Angebotsdaten fehlen.' },
      { title: 'Grenzen', content: 'Sechs KI-Rollen sind keine sechs Kunden.' }
    ]
  },
  ...overrides
})

const logResponse = (logs = [], fromLine = 0) => ({
  success: true,
  data: { logs, from_line: fromLine, total_lines: fromLine + logs.length, has_more: false }
})

const event = (action, details = {}, sectionIndex = null) => ({
  action, details, section_index: sectionIndex,
  section_title: sectionIndex ? 'Beobachtungen' : null,
  timestamp: `2026-09-07T12:00:0${sectionIndex || 0}`,
  elapsed_seconds: 0
})

let wrapper

async function openReport(reportId = 'report_saved') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }]
  })
  await router.push('/')
  wrapper = mount(Step4Report, {
    props: { reportId, simulationId: 'sim_saved', systemLogs: [] },
    global: { plugins: [router] }
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.useFakeTimers()
  getReport.mockResolvedValue({ success: true, data: savedReport() })
  getAgentLog.mockImplementation((_, fromLine = 0) => Promise.resolve(logResponse(
    fromLine === 0 ? [event('codex_evidence_report_saved', { author: 'Codex' })] : [],
    fromLine
  )))
  getConsoleLog.mockResolvedValue(logResponse())
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  vi.useRealTimers()
  vi.resetAllMocks()
})

describe('gespeicherte Reports', () => {
  it('zeigt den fertigen Bericht ohne native Kapitel- oder Abschlussereignisse', async () => {
    await openReport()
    expect(wrapper.find('h1').exists()).toBe(true)
    expect(wrapper.find('h1').text()).toBe('Buybacklinks-Auswertung')
    expect(wrapper.findAll('.generated-content')).toHaveLength(3)
    expect(wrapper.text()).toContain('Codex-Auswertung, kein nativer ReportAgent-Lauf.')
    expect(wrapper.text()).toContain('Sechs KI-Rollen sind keine sechs Kunden.')
    expect(wrapper.find('.metric-value').text()).toBe('3/3')
    expect(wrapper.find('.waiting-placeholder').exists()).toBe(false)
    expect(wrapper.emitted('update-status').at(-1)).toEqual(['completed'])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('laesst historische Protokolltexte den gespeicherten Bericht nicht ueberschreiben', async () => {
    getAgentLog.mockResolvedValue(logResponse([
      event('planning_complete', { outline: savedReport().outline }),
      event('section_complete', { content: 'VERALTETER ENTWURF' }, 1),
      event('report_complete')
    ]))
    await openReport()
    expect(wrapper.findAll('.generated-content')[0].text()).toContain('Codex-Auswertung')
    expect(wrapper.findAll('.generated-content')[0].text()).not.toContain('VERALTETER ENTWURF')
    expect(wrapper.find('.metric-value').text()).toBe('3/3')
  })

  it('zeigt fertigen Inhalt auch bei einem nicht verfuegbaren Diagnoseprotokoll', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    getAgentLog.mockRejectedValue(new Error('Protokoll nicht verfuegbar'))
    getConsoleLog.mockRejectedValue(new Error('Protokoll nicht verfuegbar'))
    await openReport()
    expect(wrapper.findAll('.generated-content')).toHaveLength(3)
    expect(wrapper.emitted('update-status').at(-1)).toEqual(['completed'])
    expect(vi.getTimerCount()).toBe(0)
  })
})

describe('laufende und fehlgeschlagene Reports', () => {
  it.each([404, 500])('uebersteht einen voruebergehenden HTTP-%i-Fehler beim Speichern', async (status) => {
    getReport.mockRejectedValueOnce(Object.assign(new Error('Bericht voruebergehend nicht lesbar'), {
      response: { status }
    }))
    await openReport()
    expect(wrapper.find('[role="alert"]').text()).toContain('Automatischer neuer Versuch')
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(wrapper.findAll('.generated-content')).toHaveLength(3)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.emitted('update-status').at(-1)).toEqual(['completed'])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('begrenzt die automatischen Wiederholungen bei einem dauerhaft fehlenden Bericht', async () => {
    getReport.mockRejectedValue(Object.assign(new Error('Bericht nicht gefunden'), { response: { status: 404 } }))
    await openReport()
    await vi.advanceTimersByTimeAsync(10000)
    await flushPromises()
    expect(getReport).toHaveBeenCalledTimes(3)
    expect(wrapper.find('[role="alert"]').text()).toContain('Bericht nicht gefunden')
    expect(wrapper.find('[role="alert"]').text()).not.toContain('Automatischer neuer Versuch')
    expect(wrapper.emitted('update-status').at(-1)).toEqual(['error'])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('wartet nach dem Abschlussereignis noch auf den tatsaechlich gespeicherten Report', async () => {
    getReport.mockResolvedValueOnce({ success: true, data: savedReport({ status: 'generating' }) })
    getAgentLog.mockResolvedValue(logResponse([event('report_complete')]))
    await openReport()
    expect(wrapper.emitted('update-status').at(-1)).toEqual(['processing'])
    expect(vi.getTimerCount()).toBe(1)
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(wrapper.findAll('.generated-content')).toHaveLength(3)
    expect(wrapper.emitted('update-status').at(-1)).toEqual(['completed'])
  })

  it('zeigt Kapitel waehrend des Laufs und erkennt den gespeicherten Abschluss ohne Schlussereignis', async () => {
    getReport.mockResolvedValueOnce({ success: true, data: savedReport({ status: 'generating' }) })
    getAgentLog.mockImplementation((_, fromLine = 0) => Promise.resolve(logResponse(
      fromLine === 0 ? [
        event('planning_complete', { outline: savedReport().outline }),
        event('section_complete', { content: 'Laufender erster Abschnitt' }, 1)
      ] : [], fromLine
    )))
    await openReport()
    expect(wrapper.find('.metric-value').text()).toBe('1/3')
    expect(wrapper.text()).toContain('Laufender erster Abschnitt')
    expect(wrapper.emitted('update-status')?.at(-1)).not.toEqual(['completed'])
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(wrapper.find('.metric-value').text()).toBe('3/3')
    expect(wrapper.emitted('update-status').at(-1)).toEqual(['completed'])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('zeigt einen gespeicherten Fehler statt endloser Generierung', async () => {
    getReport.mockResolvedValue({ success: true, data: savedReport({ status: 'failed', error: 'Generierung fehlgeschlagen', outline: null }) })
    await openReport()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper.find('[role="alert"]').text()).toContain('Generierung fehlgeschlagen')
    expect(wrapper.emitted('update-status').at(-1)).toEqual(['error'])
    expect(wrapper.find('.waiting-placeholder').exists()).toBe(false)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('meldet einen nicht ladbaren Bericht sichtbar und beendet die Abfragen', async () => {
    getReport.mockRejectedValue(new Error('Bericht nicht gefunden'))
    await openReport()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper.find('[role="alert"]').text()).toContain('Bericht nicht gefunden')
    expect(wrapper.emitted('update-status').at(-1)).toEqual(['error'])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('startet bei langsamen Antworten keine ueberlappenden Statusabfragen', async () => {
    let resolveRequest
    getReport.mockReturnValue(new Promise(resolve => { resolveRequest = resolve }))
    await openReport()
    await vi.advanceTimersByTimeAsync(6000)
    expect(getReport).toHaveBeenCalledTimes(1)
    resolveRequest({ success: true, data: savedReport() })
    await flushPromises()
    expect(wrapper.find('.metric-value').text()).toBe('3/3')
  })

  it('ignoriert eine alte Antwort nach Wechsel zu einer anderen Report-ID', async () => {
    let resolveOld
    getReport.mockImplementation(reportId => reportId === 'report_old'
      ? new Promise(resolve => { resolveOld = resolve })
      : Promise.resolve({ success: true, data: savedReport() }))
    await openReport('report_old')
    await wrapper.setProps({ reportId: 'report_saved' })
    await flushPromises()
    expect(wrapper.find('h1').exists()).toBe(true)
    expect(wrapper.find('h1').text()).toBe('Buybacklinks-Auswertung')
    resolveOld({ success: true, data: savedReport({ report_id: 'report_old', outline: { title: 'Alter Report', summary: '', sections: [] } }) })
    await flushPromises()
    expect(wrapper.find('h1').text()).toBe('Buybacklinks-Auswertung')
    expect(wrapper.findAll('.generated-content')).toHaveLength(3)
  })
})
